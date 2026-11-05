"""Speech-to-text via faster-whisper."""

from __future__ import annotations

from .textclean import strip_emojis

import ctypes
import logging
import os
from pathlib import Path
from typing import Any

from babel_agent.config import DEFAULT_WHISPER

logger = logging.getLogger(__name__)

_model: Any = None
_model_name: str | None = None
_device: str | None = None
_compute: str | None = None
_backend_note: str = ""

# Known locations for libcublas.so.12 when the system CUDA toolkit is absent
# (e.g. Ollama ships CUDA 12 libs; pip nvidia-cublas-cu12 puts them in site-packages).
_CUBLAS_CANDIDATE_DIRS = (
    "/usr/local/lib/ollama/cuda_v12",
    "/usr/local/cuda/lib64",
    "/usr/local/cuda-12/lib64",
    "/usr/lib/x86_64-linux-gnu",
)


def backend_note() -> str:
    """Human-readable note about the active STT device (empty until first load)."""
    return _backend_note


def _candidate_cuda_lib_dirs() -> list[Path]:
    dirs: list[Path] = []
    for raw in _CUBLAS_CANDIDATE_DIRS:
        p = Path(raw)
        if p.is_dir():
            dirs.append(p)
    try:
        import site

        for sp in site.getsitepackages() + [site.getusersitepackages()]:
            for rel in (
                "nvidia/cublas/lib",
                "nvidia/cuda_runtime/lib",
                "nvidia/cudnn/lib",
            ):
                p = Path(sp) / rel
                if p.is_dir():
                    dirs.append(p)
    except Exception:
        pass
    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for d in dirs:
        key = str(d.resolve()) if d.exists() else str(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _ensure_cublas_on_path() -> bool:
    """Try to make libcublas.so.12 loadable. Returns True if it loads."""
    try:
        ctypes.CDLL("libcublas.so.12")
        return True
    except OSError:
        pass

    for d in _candidate_cuda_lib_dirs():
        so = d / "libcublas.so.12"
        if not so.is_file() and not so.is_symlink():
            # Some trees only ship versioned sonames
            matches = list(d.glob("libcublas.so.12*"))
            if not matches:
                continue
            so = matches[0]
        try:
            # Prepend so ctranslate2's transitive deps resolve too
            cur = os.environ.get("LD_LIBRARY_PATH", "")
            prefix = str(d)
            if prefix not in cur.split(":"):
                os.environ["LD_LIBRARY_PATH"] = (
                    f"{prefix}:{cur}" if cur else prefix
                )
            ctypes.CDLL(str(so))
            # Also try the generic soname after path update
            try:
                ctypes.CDLL("libcublas.so.12")
            except OSError:
                pass
            logger.info("Loaded libcublas from %s", d)
            return True
        except OSError as exc:
            logger.debug("cublas probe failed in %s: %s", d, exc)
    return False


def _pick_device() -> tuple[str, str]:
    """Return (device, compute_type). Prefer CUDA only when cublas is loadable."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0 and _ensure_cublas_on_path():
            return "cuda", "float16"
    except Exception as exc:
        logger.info("CUDA not usable for Whisper (%s); using CPU", exc)
    return "cpu", "int8"


def get_model(model_size: str | None = None):
    global _model, _model_name, _device, _compute, _backend_note
    size = model_size or DEFAULT_WHISPER
    if _model is not None and _model_name == size:
        return _model

    from faster_whisper import WhisperModel

    device, compute = _pick_device()
    logger.info("Loading faster-whisper %s on %s (%s)", size, device, compute)
    try:
        _model = WhisperModel(size, device=device, compute_type=compute)
        _device = device
        _compute = compute
        if device == "cuda":
            _backend_note = "STT: Whisper on GPU (CUDA)"
        else:
            _backend_note = "STT: Whisper on CPU (int8)"
    except Exception as exc:
        if device != "cpu":
            logger.warning(
                "Whisper CUDA load failed (%s); falling back to CPU int8", exc
            )
            _model = WhisperModel(size, device="cpu", compute_type="int8")
            _device = "cpu"
            _compute = "int8"
            _backend_note = (
                "STT: Whisper on CPU (CUDA libs missing — e.g. libcublas.so.12)"
            )
        else:
            raise
    _model_name = size
    return _model


def reset_model() -> None:
    """Drop the cached Whisper model (e.g. after a device failure mid-run)."""
    global _model, _model_name, _device, _compute
    _model = None
    _model_name = None
    _device = None
    _compute = None


def _allowed_lang_codes(target_language: str, native_language: str) -> list[str]:
    """ISO codes for target + native only (order: target first, then native)."""
    from babel_agent.config import LANG_CODES

    codes: list[str] = []
    for name in (target_language, native_language):
        code = LANG_CODES.get(name)
        if code and code not in codes:
            codes.append(code)
    return codes


def _pass_score(text: str, info: Any, segments: list[Any]) -> float:
    """Higher is better. Prefer real speech, longer text, stronger avg logprob."""
    text = (text or "").strip()
    if not text:
        return -1e9
    no_speech = float(getattr(info, "no_speech_prob", 0) or 0)
    # Prefer lower no-speech
    score = len(text) * 0.15
    # Average segment avg_logprob when available
    logprobs: list[float] = []
    for seg in segments:
        lp = getattr(seg, "avg_logprob", None)
        if lp is not None:
            logprobs.append(float(lp))
    if logprobs:
        score += sum(logprobs) / len(logprobs) * 12.0
    lang_prob = float(getattr(info, "language_probability", 0) or 0)
    score += lang_prob * 2.0
    score -= no_speech * 8.0
    # Tiny / junk transcripts
    if len(text) < 3:
        score -= 5.0
    return score


def _is_weak_result(text: str, info: Any) -> bool:
    text = (text or "").strip()
    if len(text) < 3:
        return True
    lang_prob = float(getattr(info, "language_probability", 0) or 0)
    no_speech = float(getattr(info, "no_speech_prob", 0) or 0)
    if lang_prob > 0 and lang_prob < 0.45:
        return True
    if no_speech >= 0.6 and len(text) < 12:
        return True
    return False


def transcribe(
    audio_path: str | Path,
    *,
    target_language: str,
    native_language: str,
    model_size: str | None = None,
    bluetooth: bool = False,
) -> str:
    """Transcribe an audio file to text.

    Language is locked to the session target and native codes only — never
    unrestricted auto-detect (language=None). Prefer target; if that pass is
    empty/weak, also try native and keep the better score. If a CUDA-backed
    model fails at inference (missing cublas, etc.), reload on CPU and retry.
    """
    global _model, _model_name, _device, _compute, _backend_note

    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")

    if model_size is None and bluetooth:
        model_size = os.environ.get("BABEL_AGENT_WHISPER_BT", os.environ.get("LANG_TUTOR_WHISPER_BT", "small"))
    allowed = _allowed_lang_codes(target_language, native_language)
    if not allowed:
        # Last resort: still never use unrestricted auto; default Spanish code
        # only if both names were unknown (should not happen in the UI).
        logger.warning(
            "No LANG_CODES for target=%r native=%r; refusing unrestricted auto",
            target_language,
            native_language,
        )
        raise ValueError(
            f"Unsupported language pair: {target_language!r} / {native_language!r}"
        )

    prompt = (
        f"Language practice. The learner speaks {target_language} "
        f"(primary) and may briefly use {native_language}. "
        f"Transcribe only in those languages; do not switch to others."
    )

    def _run_locked(model: Any, lang_code: str) -> tuple[str, Any, list[Any]]:
        assert lang_code is not None  # never language=None
        segments_iter, info = model.transcribe(
            str(path),
            language=lang_code,
            vad_filter=True,
            beam_size=3,
            initial_prompt=prompt,
        )
        segments = list(segments_iter)
        text = strip_emojis(" ".join(seg.text.strip() for seg in segments).strip())
        logger.info(
            "STT locked lang=%s reported=%s prob=%.2f text=%r",
            lang_code,
            getattr(info, "language", "?"),
            float(getattr(info, "language_probability", 0) or 0),
            text[:120],
        )
        return text, info, segments

    def _run(model: Any) -> str:
        primary = allowed[0]
        text, info, segments = _run_locked(model, primary)
        best_text = text
        best_score = _pass_score(text, info, segments)
        best_lang = primary

        need_second = len(allowed) > 1 and _is_weak_result(text, info)
        if need_second:
            secondary = allowed[1]
            primary_score = best_score
            text2, info2, segs2 = _run_locked(model, secondary)
            score2 = _pass_score(text2, info2, segs2)
            if score2 > best_score:
                best_text, best_score, best_lang = text2, score2, secondary
            logger.info(
                "STT dual-pass chose lang=%s score=%.2f (primary %s=%.2f secondary %s=%.2f)",
                best_lang,
                best_score,
                primary,
                primary_score,
                secondary,
                score2,
            )
        elif len(allowed) > 1:
            # Strong target pass — still allow a native pass when primary text
            # looks empty of content relative to a possible native reply.
            # Skip expensive second pass when primary is clearly good.
            logger.debug("STT single-pass OK lang=%s", primary)

        return best_text

    model = get_model(model_size)
    try:
        return _run(model)
    except Exception as exc:
        msg = str(exc).lower()
        cudaish = (
            "cublas" in msg
            or "cuda" in msg
            or "cudnn" in msg
            or "cannot be loaded" in msg
        )
        if not cudaish or (_device or "") == "cpu":
            raise
        logger.warning(
            "Whisper inference failed on CUDA (%s); reloading on CPU", exc
        )
        reset_model()
        _backend_note = (
            "STT: Whisper on CPU (CUDA runtime error — fell back automatically)"
        )
        from faster_whisper import WhisperModel

        size = model_size or DEFAULT_WHISPER
        _model = WhisperModel(size, device="cpu", compute_type="int8")
        _model_name = size
        _device = "cpu"
        _compute = "int8"
        return _run(_model)
