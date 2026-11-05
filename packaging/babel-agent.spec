# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Babel Agent (run from repo root).
#   pyinstaller packaging/babel-agent.spec

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

REPO = Path(SPECPATH).resolve().parent

pyside_datas, pyside_binaries, pyside_hidden = collect_all("PySide6")
try:
    fw_datas, fw_binaries, fw_hidden = collect_all("faster_whisper")
except Exception:
    fw_datas, fw_binaries, fw_hidden = [], [], []
try:
    ct2_binaries = collect_dynamic_libs("ctranslate2")
except Exception:
    ct2_binaries = []

a = Analysis(
    [str(REPO / "app.py")],
    pathex=[str(REPO)],
    binaries=pyside_binaries + fw_binaries + ct2_binaries,
    datas=pyside_datas + fw_datas + [(str(REPO / "assets"), "assets")],
    hiddenimports=[
        "babel_agent",
        "babel_agent.ui",
        "babel_agent.tutor",
        "babel_agent.memory",
        "babel_agent.leveling",
        "babel_agent.ollama_client",
        "babel_agent.stt",
        "babel_agent.tts",
        "babel_agent.audio_capture",
        "babel_agent.practice_modes",
        "babel_agent.config",
        "faster_whisper",
        "ctranslate2",
        "sounddevice",
        "soundfile",
        "numpy",
        "httpx",
        "PySide6.QtMultimedia",
        "PySide6.QtNetwork",
    ]
    + list(pyside_hidden)
    + list(fw_hidden),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["gradio", "matplotlib", "tkinter", "PyQt5", "PyQt6"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BabelAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="BabelAgent",
)
