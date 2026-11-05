"""Paths and default settings for Babel Agent."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _default_data_dir() -> Path:
    env = os.environ.get("BABEL_AGENT_DATA", os.environ.get("LANG_TUTOR_DATA"))
    if env:
        return Path(env)
    # PyInstaller frozen binary → user data dir
    if getattr(sys, "frozen", False):
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            return Path(xdg) / "babel-agent"
        return Path.home() / ".local" / "share" / "babel-agent"
    return Path(__file__).resolve().parent.parent / "data"


ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"


def asset_path(name: str) -> Path:
    """Resolve a bundled asset (dev tree or PyInstaller)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cand = Path(meipass) / "assets" / name
            if cand.exists():
                return cand
        # installed beside the binary under /opt/babel-agent/assets
        beside = Path(sys.executable).resolve().parent / "assets" / name
        if beside.exists():
            return beside
    return ASSETS_DIR / name


DATA_DIR = _default_data_dir()
DB_PATH = DATA_DIR / "learner.db"
AUDIO_DIR = DATA_DIR / "audio"
VOICES_DIR = DATA_DIR / "piper_voices"

OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
# Kept for backwards compat; desktop app ignores bind host/port
HOST = os.environ.get("BABEL_AGENT_HOST", os.environ.get("LANG_TUTOR_HOST", "127.0.0.1"))
PORT = int(os.environ.get("BABEL_AGENT_PORT", os.environ.get("LANG_TUTOR_PORT", "7860")))

DEFAULT_TARGET = "Spanish"
DEFAULT_NATIVE = "Portuguese"
DEFAULT_LEVEL = "A1"
DEFAULT_MODE = "conversation"
DEFAULT_WHISPER = os.environ.get("BABEL_AGENT_WHISPER", os.environ.get("LANG_TUTOR_WHISPER", "base"))

CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")

LANGUAGES = (
    "Spanish",
    "Portuguese",
    "English",
    "French",
    "German",
    "Italian",
    "Japanese",
    "Chinese",
    "Korean",
    "Arabic",
    "Russian",
    "Dutch",
    "Polish",
    "Turkish",
    "Hungarian",
)

# ISO-ish codes for faster-whisper language hints
LANG_CODES = {
    "Spanish": "es",
    "Portuguese": "pt",
    "English": "en",
    "French": "fr",
    "German": "de",
    "Italian": "it",
    "Japanese": "ja",
    "Chinese": "zh",
    "Korean": "ko",
    "Arabic": "ar",
    "Russian": "ru",
    "Dutch": "nl",
    "Polish": "pl",
    "Turkish": "tr",
    "Hungarian": "hu",
}

# Piper voice name hints (downloaded on demand if piper-tts supports it)
PIPER_VOICE_HINTS = {
    "es": "es_ES-sharvard-medium",
    "pt": "pt_BR-faber-medium",
    "en": "en_US-lessac-medium",
    "fr": "fr_FR-siwis-medium",
    "de": "de_DE-thorsten-medium",
    "it": "it_IT-riccardo-x_low",
}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    VOICES_DIR.mkdir(parents=True, exist_ok=True)


SETTINGS_PATH = DATA_DIR / "settings.json"


def load_settings() -> dict:
    import json

    try:
        return json.loads(SETTINGS_PATH.read_text())
    except Exception:
        return {}


def save_settings(updates: dict) -> None:
    import json

    data = load_settings()
    data.update(updates)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass
