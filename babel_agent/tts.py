"""Text-to-speech: prefer Piper (offline), else pyttsx3, optional edge-tts."""

from __future__ import annotations

from .textclean import strip_emojis

import logging
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path

from babel_agent.config import AUDIO_DIR, LANG_CODES, PIPER_VOICE_HINTS, VOICES_DIR, ensure_dirs

logger = logging.getLogger(__name__)

_BACKEND: str | None = None

# Prefer female speaker for multi-speaker Piper voices (es_ES-sharvard: M=0, F=1).
_PIPER_SPEAKER_ID = 1
_PIPER_LENGTH_SCALE = 1.05
_KEEP_REPLY_WAVS = 10

# Module-level Piper voice cache: model path → PiperVoice
_PIPER_VOICE_CACHE: dict[str, object] = {}


def available_backends() -> list[str]:
    found: list[str] = []
    try:
        import piper  # noqa: F401

        found.append("piper")
    except Exception:
        if shutil.which("piper"):
            found.append("piper-cli")
    try:
        import pyttsx3  # noqa: F401

        found.append("pyttsx3")
    except Exception:
        pass
    try:
        import edge_tts  # noqa: F401

        found.append("edge-tts (online)")
    except Exception:
        pass
    return found


def _strip_for_speech(text: str) -> str:
    # Drop markdown-ish noise
    text = re.sub(r"[*_`#]+", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    """Split into Spanish-friendly sentences; keep leading ¡¿ with the sentence."""
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []

    # Match optional opening marks, body, then terminal punctuation, or a final remnant.
    pattern = re.compile(
        r"(?:[¡¿]+\s*)?[^.!?…¡¿]+(?:[.!?…]+|(?=(?:[¡¿])))|(?:[¡¿]+\s*)?[^.!?…¡¿]+$",
        re.UNICODE,
    )
    parts = [m.group(0).strip() for m in pattern.finditer(text) if m.group(0).strip()]
    if not parts:
        return [text]
    # Merge tiny leftovers (e.g. lone punctuation) into the previous sentence.
    merged: list[str] = []
    for p in parts:
        if merged and len(p) <= 2 and not re.search(r"[A-Za-zÀ-ÿ0-9]", p):
            merged[-1] = (merged[-1] + " " + p).strip()
        else:
            merged.append(p)
    return merged or [text]


def _unique_reply_path(suffix: str = ".wav") -> Path:
    ensure_dirs()
    ts = int(time.time() * 1000)
    return AUDIO_DIR / f"reply-{ts}{suffix}"


def _prune_old_replies(keep: int = _KEEP_REPLY_WAVS) -> None:
    try:
        files = sorted(
            AUDIO_DIR.glob("reply-*.wav"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in files[keep:]:
            try:
                old.unlink(missing_ok=True)
            except OSError:
                pass
        # Also drop the legacy fixed name if present.
        legacy = AUDIO_DIR / "reply.wav"
        if legacy.is_file():
            try:
                legacy.unlink()
            except OSError:
                pass
    except OSError as exc:
        logger.debug("Could not prune reply wavs: %s", exc)


def _find_piper_model(lang_code: str) -> Path:
    voice = PIPER_VOICE_HINTS.get(lang_code) or PIPER_VOICE_HINTS["en"]
    for p in VOICES_DIR.glob(f"{voice}*.onnx"):
        return p
    onnx = list(VOICES_DIR.glob("*.onnx"))
    if onnx:
        return onnx[0]
    raise RuntimeError(
        "No Piper voice model available under data/piper_voices "
        "(download voices offline beforehand; synthesize never fetches)"
    )


def _get_piper_voice(model_path: Path):
    key = str(model_path.resolve())
    cached = _PIPER_VOICE_CACHE.get(key)
    if cached is not None:
        return cached
    from piper import PiperVoice

    voice_obj = PiperVoice.load(key)
    _PIPER_VOICE_CACHE[key] = voice_obj
    return voice_obj


def _piper_syn_config():
    from piper import SynthesisConfig

    return SynthesisConfig(speaker_id=_PIPER_SPEAKER_ID, length_scale=_PIPER_LENGTH_SCALE)


def _write_silence(wf: wave.Wave_write, seconds: float = 0.15) -> None:
    try:
        rate = wf.getframerate()
        width = wf.getsampwidth()
        channels = wf.getnchannels()
    except wave.Error:
        return
    n = max(0, int(rate * seconds))
    if n:
        wf.writeframes(b"\x00" * (n * width * channels))


def _synthesize_piper(text: str, out_path: Path, lang_code: str) -> Path:
    ensure_dirs()

    # Try Python API first. Never download on the hot path — use local *.onnx only.
    try:
        model_path = _find_piper_model(lang_code)
        voice_obj = _get_piper_voice(model_path)
        syn_config = _piper_syn_config()
        sentences = _split_sentences(text) or [text]

        with wave.open(str(out_path), "wb") as wf:
            first = True
            for i, sentence in enumerate(sentences):
                if not sentence.strip():
                    continue
                voice_obj.synthesize_wav(
                    sentence.strip(),
                    wf,
                    syn_config=syn_config,
                    set_wav_format=first,
                )
                first = False
                if i < len(sentences) - 1:
                    _write_silence(wf, 0.15)
        if first:
            raise RuntimeError("Piper produced no audio frames")
        return out_path
    except Exception as exc:
        logger.info("Piper Python API unavailable (%s); trying CLI", exc)

    piper_bin = shutil.which("piper")
    if not piper_bin:
        raise RuntimeError("piper not installed")

    onnx = next(VOICES_DIR.glob("*.onnx"), None)
    if onnx is None:
        raise RuntimeError("No Piper .onnx voice in data/piper_voices")

    # CLI: synthesize sentence-by-sentence into temp buffers, then concatenate.
    sentences = _split_sentences(text) or [text]
    pcm_chunks: list[bytes] = []
    params: tuple[int, int, int] | None = None  # nchannels, sampwidth, framerate
    for sentence in sentences:
        if not sentence.strip():
            continue
        tmp_path = out_path.with_name(out_path.stem + f".part{len(pcm_chunks)}.wav")
        cmd = [
            piper_bin,
            "--model",
            str(onnx),
            "--output_file",
            str(tmp_path),
            "--speaker",
            str(_PIPER_SPEAKER_ID),
            "--length_scale",
            str(_PIPER_LENGTH_SCALE),
        ]
        proc = subprocess.run(
            cmd,
            input=sentence.strip().encode("utf-8"),
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0 or not tmp_path.is_file():
            err = proc.stderr.decode("utf-8", errors="replace")[:400]
            # Retry without speaker/length flags for older CLI builds.
            if "--speaker" in " ".join(cmd):
                proc = subprocess.run(
                    [piper_bin, "--model", str(onnx), "--output_file", str(tmp_path)],
                    input=sentence.strip().encode("utf-8"),
                    capture_output=True,
                    check=False,
                )
            if proc.returncode != 0 or not tmp_path.is_file():
                raise RuntimeError(err or proc.stderr.decode("utf-8", errors="replace")[:400])
        with wave.open(str(tmp_path), "rb") as part:
            if params is None:
                params = (part.getnchannels(), part.getsampwidth(), part.getframerate())
            pcm_chunks.append(part.readframes(part.getnframes()))
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    if not pcm_chunks or params is None:
        raise RuntimeError("piper CLI produced no audio")

    nchannels, sampwidth, framerate = params
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        silence = b"\x00" * int(framerate * 0.15) * sampwidth * nchannels
        for i, chunk in enumerate(pcm_chunks):
            wf.writeframes(chunk)
            if i < len(pcm_chunks) - 1:
                wf.writeframes(silence)
    return out_path


def _synthesize_pyttsx3(text: str, out_path: Path) -> Path:
    import pyttsx3

    engine = pyttsx3.init()
    # Prefer wav path; on Linux espeak backend may write wav
    target = out_path
    engine.save_to_file(text, str(target))
    engine.runAndWait()
    if not target.is_file():
        raise RuntimeError("pyttsx3 did not write audio file")
    return target


def _synthesize_edge(text: str, out_path: Path, lang_code: str) -> Path:
    import asyncio

    import edge_tts

    voice_map = {
        "es": "es-ES-ElviraNeural",
        "pt": "pt-BR-FranciscaNeural",
        "en": "en-US-JennyNeural",
        "fr": "fr-FR-DeniseNeural",
        "de": "de-DE-KatjaNeural",
        "it": "it-IT-ElsaNeural",
    }
    voice = voice_map.get(lang_code, "en-US-JennyNeural")
    mp3 = out_path.with_suffix(".mp3")

    async def _run() -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(mp3))

    asyncio.run(_run())
    return mp3


def synthesize(
    text: str,
    *,
    target_language: str,
    prefer: str | None = None,
) -> tuple[str | None, str]:
    """Synthesize speech. Returns (audio_path_or_None, backend_note)."""
    ensure_dirs()
    clean = _strip_for_speech(strip_emojis(text or ""))
    if not clean:
        return None, "empty text"

    lang_code = LANG_CODES.get(target_language, "en")
    out_path = _unique_reply_path(".wav")
    order = []
    if prefer:
        order.append(prefer)
    order.extend(["piper", "pyttsx3", "edge-tts"])

    errors: list[str] = []
    seen: set[str] = set()
    for backend in order:
        if backend in seen:
            continue
        seen.add(backend)
        try:
            if backend == "piper":
                path = _synthesize_piper(clean, out_path, lang_code)
                _prune_old_replies()
                return str(path), "piper (offline)"
            if backend == "pyttsx3":
                path = _synthesize_pyttsx3(clean, out_path)
                _prune_old_replies()
                return str(path), "pyttsx3 (offline fallback)"
            if backend == "edge-tts":
                edge_out = _unique_reply_path(".mp3")
                path = _synthesize_edge(clean, edge_out, lang_code)
                _prune_old_replies()
                return str(path), "edge-tts (ONLINE fallback — needs network)"
        except Exception as exc:
            errors.append(f"{backend}: {exc}")
            logger.warning("TTS backend %s failed: %s", backend, exc)

    note = "TTS failed. " + " | ".join(errors[:3])
    note += (
        " Install piper-tts and a voice under data/piper_voices, "
        "or pyttsx3 / edge-tts. See README."
    )
    return None, note
