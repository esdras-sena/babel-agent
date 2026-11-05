"""Click-to-toggle microphone capture → 16 kHz WAV file for STT."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

from babel_agent.config import AUDIO_DIR

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1


def _is_monitor(name: str) -> bool:
    return "monitor" in name.lower()


def _pactl_default_source() -> str | None:
    if not shutil.which("pactl"):
        return None
    try:
        out = subprocess.run(
            ["pactl", "get-default-source"], capture_output=True, text=True, timeout=2
        )
        name = out.stdout.strip()
        return name or None
    except Exception:
        return None


def list_input_devices() -> list[dict]:
    """Input-capable devices, excluding speaker monitors/loopbacks."""
    import sounddevice as sd

    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception as exc:
        logger.warning("query_devices failed: %s", exc)
        return []
    out: list[dict] = []
    for idx, d in enumerate(devices):
        if int(d.get("max_input_channels", 0)) <= 0:
            continue
        name = str(d.get("name", ""))
        if _is_monitor(name):
            continue
        try:
            api = hostapis[d["hostapi"]]["name"]
        except Exception:
            api = "?"
        low = name.lower()
        out.append(
            {
                "index": idx,
                "name": name,
                "hostapi": api,
                "default_rate": float(d.get("default_samplerate") or SAMPLE_RATE),
                "is_monitor": False,
                "is_bluetooth": "bluez" in low or "bluetooth" in low,
            }
        )
    return out


def device_label(dev: dict) -> str:
    return friendly_mic_name(dev["name"])


def resolve_input_device(preferred: int | str | None = None) -> int | None:
    """Pick a valid (non-monitor) input device index. None = PortAudio default."""
    devs = list_input_devices()
    if not devs:
        return None
    if preferred is not None and preferred != "":
        for d in devs:
            if isinstance(preferred, int) and d["index"] == preferred:
                return d["index"]
            if isinstance(preferred, str) and d["name"] == preferred:
                return d["index"]
    for d in devs:  # prefer the Bluetooth headset when one is connected
        if d["name"].startswith("bluez_input"):
            return d["index"]
    src = _pactl_default_source()
    if src:
        for d in devs:
            if src in d["name"] or d["name"] in src:
                return d["index"]
    for d in devs:
        if "pulse" in d["hostapi"].lower() or "pipewire" in d["hostapi"].lower():
            if d["name"].lower() in ("default source", "default", "pulse", "pipewire"):
                return d["index"]
    for d in devs:
        if d["name"].lower() in ("default source", "pulse", "pipewire", "default"):
            return d["index"]
    try:
        import sounddevice as sd

        idx = sd.default.device[0]
        if idx is not None and idx >= 0 and any(d["index"] == idx for d in devs):
            return int(idx)
    except Exception:
        pass
    return devs[0]["index"]


def _resample(audio: np.ndarray, src: float, dst: int) -> np.ndarray:
    if int(src) == dst or audio.size == 0:
        return audio
    try:
        import soxr  # type: ignore

        return soxr.resample(audio, src, dst).astype(np.float32)
    except Exception:
        pass
    n = int(round(len(audio) * dst / src))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def _soft_normalize(audio: np.ndarray) -> np.ndarray:
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if 1e-3 < peak < 0.25:
        gain = min(0.8 / peak, 8.0)
        audio = np.clip(audio * gain, -1.0, 1.0)
        logger.info("Soft-normalized quiet recording (peak %.3f, gain %.1fx)", peak, gain)
    return audio



_BT_MAC_RE = None


def _bt_mac(name: str) -> str | None:
    import re

    m = re.search(r"([0-9A-Fa-f]{2}(?:[:_][0-9A-Fa-f]{2}){5})", name or "")
    return m.group(1).replace("_", ":").upper() if m else None


_friendly_cache: dict[str, str] = {}


def bt_friendly_name(name: str) -> str | None:
    """'JBL Tune 520BT' for a bluez source name, via bluetoothctl/pactl (cached)."""
    mac = _bt_mac(name)
    if not mac:
        return None
    if mac in _friendly_cache:
        return _friendly_cache[mac]
    alias = None
    try:
        if shutil.which("bluetoothctl"):
            out = subprocess.run(["bluetoothctl", "info", mac], capture_output=True, text=True, timeout=2).stdout
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("Alias:") or line.startswith("Name:"):
                    alias = line.split(":", 1)[1].strip()
                    break
    except Exception:
        pass
    if not alias and shutil.which("pactl"):
        try:
            out = subprocess.run(["pactl", "list", "cards"], capture_output=True, text=True, timeout=2).stdout
            us = mac.replace(":", "_")
            block = ""
            for chunk in out.split("Card #"):
                if us in chunk or mac in chunk:
                    block = chunk
                    break
            for line in block.splitlines():
                if "device.description" in line or "bluez.alias" in line:
                    alias = line.split("=", 1)[1].strip().strip('"')
                    break
        except Exception:
            pass
    _friendly_cache[mac] = alias or ""
    return alias or None


def is_bluetooth_name(name: str) -> bool:
    low = (name or "").lower()
    return "bluez" in low or "bluetooth" in low


def friendly_mic_name(name: str) -> str:
    if is_bluetooth_name(name):
        fr = bt_friendly_name(name)
        return f"{fr} mic" if fr else f"Bluetooth · {name}"
    return name


def _pulse_source_for(name: str, hostapi: str = "") -> str | None:
    """Pulse/PipeWire source name to bind parec to, or None for plain ALSA hw."""
    if not name:
        return None
    if name.startswith(("bluez_input", "bluez_source", "alsa_input.")):
        return name
    low = name.lower()
    if low in ("default source", "default", "pulse", "pipewire") or "pulse" in hostapi.lower():
        return _pactl_default_source()
    return None


def _prepare_pulse_source(src: str) -> None:
    if not shutil.which("pactl"):
        return
    try:
        subprocess.run(["pactl", "set-source-mute", src, "0"], capture_output=True, timeout=2)
        out = subprocess.run(["pactl", "get-source-volume", src], capture_output=True, text=True, timeout=2).stdout
        import re

        pcts = [int(x) for x in re.findall(r"(\d+)%", out)]
        if pcts and min(pcts) < 80:
            subprocess.run(["pactl", "set-source-volume", src, "90%"], capture_output=True, timeout=2)
            logger.info("Raised source %s volume %s%% -> 90%%", src, min(pcts))
    except Exception as exc:
        logger.info("pactl prep for %s failed: %s", src, exc)


def _highpass(audio: np.ndarray, rate: int, cutoff: float = 90.0) -> np.ndarray:
    if audio.size < 2:
        return audio
    rc = 1.0 / (2 * np.pi * cutoff)
    dt = 1.0 / rate
    a = rc / (rc + dt)
    try:
        from scipy.signal import lfilter  # type: ignore

        return lfilter([a, -a], [1.0, -a], audio).astype(np.float32)
    except Exception:
        out = np.empty_like(audio)
        prev_y = 0.0
        prev_x = float(audio[0])
        out[0] = 0.0
        for i in range(1, len(audio)):
            x = float(audio[i])
            prev_y = a * (prev_y + x - prev_x)
            prev_x = x
            out[i] = prev_y
        return out


def _agc(audio: np.ndarray, max_gain: float) -> np.ndarray:
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if peak > 1e-4:
        gain = min(0.8 / peak, max_gain)
        if gain > 1.0:
            audio = np.clip(audio * gain, -1.0, 1.0)
            logger.info("AGC peak %.3f gain %.1fx", peak, gain)
    return audio


class AudioRecorder:
    """Thread-safe record start/stop. Pulse/bluez sources use parec bound to the exact source."""

    def __init__(self, device: int | str | None = None, sample_rate: int = SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate
        self.device = device
        self.active_device_name = ""
        self.active_is_bluetooth = False
        self.backend = ""
        self.last_meta: dict = {}
        self._stream_rate: float = sample_rate
        self._lock = threading.Lock()
        self._recording = False
        self._frames: list[np.ndarray] = []
        self._stream = None
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._level = 0.0
        self._peak = 0.0

    def set_device(self, device: int | str | None) -> None:
        self.device = device

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    def level(self) -> tuple[float, float]:
        """(recent RMS, running peak) in 0..1, thread-safe."""
        with self._lock:
            return self._level, self._peak

    def _push(self, chunk: np.ndarray) -> None:
        if chunk.size == 0:
            return
        rms = float(np.sqrt(np.mean(chunk * chunk)))
        pk = float(np.abs(chunk).max())
        with self._lock:
            if self._recording:
                self._frames.append(chunk)
                self._level = rms
                self._peak = max(self._peak, pk)

    def start(self) -> None:
        if self.is_recording:
            return
        import sounddevice as sd

        dev = resolve_input_device(self.device)
        hostapi = ""
        try:
            info = sd.query_devices(dev, "input") if dev is not None else sd.query_devices(kind="input")
            name = str(info.get("name", ""))
            dev_rate = float(info.get("default_samplerate") or 48000)
            try:
                hostapi = sd.query_hostapis()[info["hostapi"]]["name"]
            except Exception:
                pass
        except Exception:
            name, dev_rate = "default", 48000.0
        src = _pulse_source_for(name, hostapi)
        self.active_device_name = src or name
        self.active_is_bluetooth = is_bluetooth_name(self.active_device_name)
        with self._lock:
            self._frames = []
            self._level = 0.0
            self._peak = 0.0

        if src and shutil.which("parec"):
            _prepare_pulse_source(src)
            proc = subprocess.Popen(
                ["parec", f"--device={src}", "--format=s16le", f"--rate={SAMPLE_RATE}",
                 "--channels=1", "--raw", "--latency-msec=50"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            self._proc = proc
            self._stream_rate = SAMPLE_RATE
            self.backend = "parec"
            with self._lock:
                self._recording = True

            def reader() -> None:
                buf = b""
                while True:
                    data = proc.stdout.read(1600) if proc.stdout else b""
                    if not data:
                        break
                    buf += data
                    n = len(buf) // 2 * 2
                    if n:
                        self._push(np.frombuffer(buf[:n], dtype="<i2").astype(np.float32) / 32768.0)
                        buf = buf[n:]

            self._reader = threading.Thread(target=reader, daemon=True)
            self._reader.start()
            logger.info("Recording started via parec on %s", src)
            return

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            self._push(indata[:, 0].copy())

        stream = None
        last_exc: Exception | None = None
        for rate in (SAMPLE_RATE, dev_rate):
            try:
                stream = sd.InputStream(device=dev, samplerate=rate, channels=CHANNELS,
                                        dtype="float32", callback=callback)
                self._stream_rate = rate
                break
            except Exception as exc:
                last_exc = exc
        if stream is None:
            raise RuntimeError(f"Could not open mic {self.active_device_name}: {last_exc}")
        self.backend = "sounddevice"
        with self._lock:
            self._recording = True
            self._stream = stream
        stream.start()
        logger.info("Recording started on [%s] %s @ %d Hz", dev, name, int(self._stream_rate))

    def _halt(self) -> list[np.ndarray]:
        with self._lock:
            self._recording = False
            stream, self._stream = self._stream, None
            proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
            if self._reader:
                self._reader.join(timeout=2)
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                logger.warning("Error closing audio stream: %s", exc)
        with self._lock:
            frames, self._frames = list(self._frames), []
        return frames

    def stop(self) -> Path | None:
        """Stop recording and write a 16 kHz WAV file. Returns path or None if empty."""
        import soundfile as sf

        frames = self._halt()
        self.last_meta = {"device_name": friendly_mic_name(self.active_device_name), "peak": 0.0,
                          "duration": 0.0, "bluetooth": self.active_is_bluetooth, "backend": self.backend}
        if not frames:
            return None
        audio = np.concatenate(frames).astype(np.float32)
        raw_peak = float(np.abs(audio).max()) if audio.size else 0.0
        self.last_meta["peak"] = raw_peak
        if audio.size == 0 or raw_peak < 1e-6:
            return None
        audio = _resample(audio, self._stream_rate, self.sample_rate)
        audio = _highpass(audio, self.sample_rate, 90.0)
        audio = _agc(audio, 12.0 if self.active_is_bluetooth else 8.0)
        self.last_meta["duration"] = len(audio) / self.sample_rate

        try:
            AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            path = AUDIO_DIR / f"rec-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time()*1000)%1000:03d}.wav"
        except Exception:
            import tempfile

            path = Path(tempfile.mkstemp(suffix=".wav", prefix="babel_agent_rec_")[1])
        sf.write(str(path), audio, self.sample_rate)
        logger.info("Recording saved: %s %s", path, self.last_meta)
        return path

    def cancel(self) -> None:
        self._halt()


# ---------------------------------------------------------------------------
# Hands-free phone-call VAD (voice activity / silence detection)
# ---------------------------------------------------------------------------

# Tunable constants for Call / Phone-call mode
VAD_SPEECH_RMS = 0.012          # RMS above this ≈ speech
VAD_MIN_SPEECH_S = 0.45         # must have spoken at least this long
VAD_SILENCE_S = 3.0             # end turn after 3 s of trailing silence (user pause tolerance)
VAD_MAX_UTTERANCE_S = 22.0      # force-stop after this much speech time
VAD_POST_PLAYBACK_DELAY_MS = 280  # settle after TTS before arming mic
VAD_POLL_MS = 80


class VadController:
    """Pure state machine: feed(rms, dt) → True when the utterance should end."""

    def __init__(
        self,
        speech_rms: float = VAD_SPEECH_RMS,
        min_speech_s: float = VAD_MIN_SPEECH_S,
        silence_s: float = VAD_SILENCE_S,
        max_utterance_s: float = VAD_MAX_UTTERANCE_S,
    ) -> None:
        self.speech_rms = speech_rms
        self.min_speech_s = min_speech_s
        self.silence_s = silence_s
        self.max_utterance_s = max_utterance_s
        self.reset()

    def reset(self) -> None:
        self.speech_seen = False
        self.speech_accum = 0.0
        self.speech_elapsed = 0.0  # wall time since first speech
        self.silence_accum = 0.0
        self.elapsed = 0.0
        self.done = False
        self.reason = ""

    def feed(self, rms: float, dt: float) -> bool:
        """Update with one level sample. Returns True when listening should stop."""
        if self.done or dt <= 0:
            return self.done
        self.elapsed += dt
        speaking = rms >= self.speech_rms
        if speaking:
            self.speech_seen = True
            self.speech_accum += dt
            self.speech_elapsed += dt
            self.silence_accum = 0.0
        elif self.speech_seen:
            self.speech_elapsed += dt
            self.silence_accum += dt

        if (
            self.speech_seen
            and self.speech_accum >= self.min_speech_s
            and self.silence_accum >= self.silence_s
        ):
            self.done = True
            self.reason = "silence"
            return True
        if self.speech_seen and self.speech_elapsed >= self.max_utterance_s:
            self.done = True
            self.reason = "max_utterance"
            return True
        return False
