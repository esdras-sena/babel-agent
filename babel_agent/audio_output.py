"""Output (sink) selection and reliable playback via paplay/pw-play on Linux."""

from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


def _run(args: list[str], timeout: float = 2.0) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def default_sink() -> str | None:
    if not shutil.which("pactl"):
        return None
    return _run(["pactl", "get-default-sink"]).strip() or None


def list_sinks() -> list[dict]:
    """Return [{'name','label'}] for real output sinks (no monitors)."""
    if not shutil.which("pactl"):
        return []
    names = [ln.split("\t")[1] for ln in _run(["pactl", "list", "short", "sinks"]).splitlines() if "\t" in ln]
    descs: dict[str, str] = {}
    cur = None
    for ln in _run(["pactl", "list", "sinks"]).splitlines():
        s = ln.strip()
        if s.startswith("Name:"):
            cur = s.split(":", 1)[1].strip()
        elif s.startswith("Description:") and cur:
            descs[cur] = s.split(":", 1)[1].strip()
    out = []
    for n in names:
        if n.endswith(".monitor"):
            continue
        label = descs.get(n, n)
        if n.startswith("bluez_output"):
            label = f"{label} (Bluetooth)"
        out.append({"name": n, "label": label})
    return out


def resolve_sink(preferred: str | None) -> str | None:
    """Preferred sink if present; else a bluez sink for the same device; else default."""
    sinks = [s["name"] for s in list_sinks()]
    if preferred and preferred != "__default__":
        if preferred in sinks:
            return preferred
        # Profile switch (A2DP <-> HFP) can rename the bluez sink; match by MAC.
        if preferred.startswith("bluez_output."):
            mac = preferred.split(".")[1]
            for s in sinks:
                if s.startswith("bluez_output.") and mac in s:
                    return s
    return default_sink()


def has_cli_player() -> bool:
    return bool(shutil.which("paplay") or shutil.which("pw-play"))


class CliPlayer:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._proc = None

    def is_playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def play(self, path: str, sink: str | None) -> bool:
        self.stop()
        if shutil.which("paplay"):
            args = ["paplay"] + ([f"--device={sink}"] if sink else []) + ["--client-name=Babel Agent", path]
        elif shutil.which("pw-play"):
            args = ["pw-play"] + (["--target", sink] if sink else []) + [path]
        else:
            return False
        try:
            self._proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Playing %s on sink %s via %s", path, sink, args[0])
            return True
        except Exception as exc:
            logger.warning("CLI playback failed: %s", exc)
            return False
