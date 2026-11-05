# Babel Agent

A **native desktop** language-learning AI agent for **Linux**, **macOS**, and **Windows**.

You speak → speech-to-text (**faster-whisper**) → a **local Ollama** model tutors you → the reply is spoken back (**TTS**). The app keeps learner memory (mistakes / successes / vocabulary) and **automatic CEFR leveling** A1–C2.

This is **not** a browser app. The UI is a real desktop window (PySide6).

Inspired by the idea of [langteacher](https://github.com/janosdios/langteacher); this is an **original** codebase (not a fork).

Current version: **0.3.1**

---

## What you get

- **Phone-call mode** (default): tutor speaks, then listens until you finish (silence ~3s) — no Record tap required
- Optional **Push-to-talk** mode with a Record button
- **Start session** / **End session** / **Mute call**
- Dropdown of Ollama models from your machine — **this app never installs or pulls models**
- Mic and Output device pickers (Bluetooth headsets supported on Linux)
- Target language, native language, practice mode, CEFR (+ automatic leveling)
- Corrections explained in your **native** language; practice stays in the **target** language
- Chat transcript + mistakes/successes panel
- SQLite memory under `./data/` (dev) or the OS user data dir (installed)

### Practice modes

- Free conversation
- Role-play
- Vocabulary quiz
- Translation practice

### Defaults

- Target: **Spanish**
- Native: **Portuguese**
- Starting level: **A1** (auto-leveling on)

---

## Prerequisites (all platforms)

1. **Ollama** + at least one **local chat model** (see sections below)
2. **Microphone and speakers** (or a Bluetooth headset)
3. **Python 3.10–3.12** if you run from source (3.11 recommended). Packaged builds bundle their own runtime.

> Babel Agent **never** runs `ollama pull` and never ships a model. If Ollama is down or has zero models, the UI tells you clearly.

---

## Install Ollama

Official site: [https://ollama.com/download](https://ollama.com/download) · Docs: [https://docs.ollama.com](https://docs.ollama.com)

### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
# start if needed:
ollama serve
# or (systemd, if the installer set it up):
# sudo systemctl enable --now ollama
```

### macOS

```bash
# Option 1 — installer script (CLI):
curl -fsSL https://ollama.com/install.sh | sh

# Option 2 — GUI: download Ollama.dmg from https://ollama.com/download
# drag Ollama into Applications, open it once
```

### Windows

Requirements: Windows 10 22H2+ (Home or Pro). NVIDIA users: recent Game Ready / Studio driver.

```powershell
# Option 1 — PowerShell installer:
irm https://ollama.com/install.ps1 | iex

# Option 2 — GUI: download OllamaSetup.exe from https://ollama.com/download
```

After install, the API listens at `http://127.0.0.1:11434`.

### Verify Ollama

```bash
ollama -v
ollama list
curl http://127.0.0.1:11434/api/tags
```

---

## Install local Ollama models

Babel Agent only **lists** models already on your machine (`GET /api/tags`). You pull them yourself:

```bash
ollama pull <model-name>
```

Useful commands:

```bash
ollama list                 # what is installed
ollama show <model-name>    # details
ollama rm <model-name>      # free disk space
ollama run <model-name>     # quick terminal chat test
```

In the Babel Agent window: click **Refresh**, then pick the model from the dropdown.

Disk tip: each model is several GB. Leave headroom beyond the download size for context/KV cache while chatting.

---

## Recommended models (for Babel Agenting)

Pick by **VRAM / unified memory**. Tutoring needs a solid chat model that follows instructions in two languages; smaller is fine for A1 practice, larger is better for nuanced corrections.

| Your GPU / memory (approx.) | Recommended pull | Why |
|----------------------------|------------------|-----|
| CPU only / ≤4 GB VRAM | `llama3.2:3b` or `qwen2.5:3b` | Fits weak machines; OK for short A1–A2 turns |
| ~6–8 GB VRAM (e.g. RTX 4050 6 GB) | `llama3.2` (3B/default) or `qwen2.5:7b` | Good speed/quality balance for phone-call tutoring |
| ~8–12 GB VRAM | `qwen2.5:7b` or `qwen2.5:14b` | Stronger grammar explanations in the native language |
| ≥16 GB VRAM / Apple Silicon 32 GB+ | `qwen2.5:14b` / `qwen2.5:32b` or similar large instruct models | Best correction quality; slower load |

**Starter commands** (choose one tier):

```bash
# Light / laptop without much VRAM
ollama pull llama3.2:3b

# Recommended default for most people
ollama pull llama3.2
# or
ollama pull qwen2.5:7b

# Stronger tutoring (needs more VRAM/RAM)
ollama pull qwen2.5:14b
```

### Notes for this app

- Prefer **instruct / chat** models, not embedding-only or vision-only tags.
- Large “thinking” models can be slow for spoken turns; Babel Agent requests replies with thinking disabled when the API supports it, but a smaller instruct model is often smoother for phone-call mode.
- Multilingual models (Llama 3.x, Qwen 2.5, etc.) work well when Target/Native are Spanish + Portuguese.
- Cloud Ollama models (`:cloud`) are optional and **not** required; this app is built for **local** `127.0.0.1:11434`.

Browse more tags: [https://ollama.com/library](https://ollama.com/library)

---

## Quick start from source (any OS)

```bash
git clone https://github.com/esdras-sena/babel-agent.git babel-agent
cd babel-agent
```

### Linux / macOS

```bash
./run.sh
# creates .venv, installs requirements, opens the desktop window
```

### Windows (PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
python -m babel_agent
```

Then in the app: **Refresh models** → pick a model → set Target / Native → **Start session**.

---

## Install on Linux

### Option A — run from source (simplest while developing)

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv libportaudio2
# optional TTS helpers:
# sudo apt install -y espeak-ng

git clone https://github.com/esdras-sena/babel-agent.git babel-agent
cd babel-agent
./run.sh
```

PulseAudio / PipeWire tools help with Bluetooth mic/output routing:

```bash
sudo apt install -y pulseaudio-utils   # provides paplay / parec
```

### Option B — install a `.deb` (packaged app)

If you have a built package (see Build below or a release `dist/` folder):

```bash
sudo apt install ./dist/babel-agent_0.3.1_amd64.deb
# or:
sudo dpkg -i ./dist/babel-agent_0.3.1_amd64.deb
sudo apt -f install
```

Launch from the app menu (**Babel Agent**) or:

```bash
babel-agent
```

Learner data: `~/.local/share/babel-agent/`

### Build the `.deb` yourself (on Linux amd64)

```bash
cd babel-agent
./packaging/linux/build_deb.sh
# → dist/babel-agent_<version>_amd64.deb
# → dist/BabelAgent/BabelAgent  (onedir binary)
```

---

## Install on macOS

### Option A — run from source

```bash
# PortAudio for the microphone
brew install portaudio
# Python 3.11 if needed
brew install python@3.11

git clone https://github.com/esdras-sena/babel-agent.git babel-agent
cd babel-agent
./run.sh
```

### Option B — build a `.app` / `.dmg` (must run on a Mac)

```bash
cd babel-agent
./packaging/macos/build_macos.sh
# → dist/BabelAgent.app
# → dist/BabelAgent-<version>-macos.dmg  (if hdiutil is available)

open dist/BabelAgent.app
```

Drag the `.app` into **Applications**, or distribute the `.dmg`.

**Note:** Gatekeeper may block an unsigned app. Right-click → Open the first time, or sign/notarize for wider distribution.

Learner data (installed / frozen): under your user Application Support path used by the app (`BABEL_AGENT_DATA` can override).

---

## Install on Windows

### Option A — run from source

1. Install [Python 3.11](https://www.python.org/downloads/) (check “Add Python to PATH”).
2. Install [Ollama for Windows](https://ollama.com) and pull a model in PowerShell: `ollama pull llama3.2`
3. Then:

```powershell
git clone https://github.com/esdras-sena/babel-agent.git babel-agent
cd babel-agent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
python -m babel_agent
```

`sounddevice` wheels on Windows usually bundle PortAudio; no extra system package is required in most cases.

### Option B — build a portable `.exe` folder (must run on Windows)

```powershell
cd babel-agent
powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1
# → dist\BabelAgent\BabelAgent.exe
```

Zip the whole `dist\BabelAgent\` folder to share, or wrap it with Inno Setup / NSIS for a Setup.exe.

---

## First-run checklist

1. Start **Ollama** and confirm `ollama list` shows at least one model.
2. Launch **Babel Agent**.
3. Click **Refresh** next to the model list and select a model.
4. Set **Target** (language you are learning) and **Native** (your language).
5. Pick **Talk mode**: **Phone call** (hands-free) or **Push-to-talk**.
6. Choose Mic / Output if you use a headset.
7. **Start session** — the tutor greets you and (in Phone call mode) starts listening after it finishes speaking.
8. Speak your answer; after ~3 seconds of silence it transcribes and replies.
9. **Mute call** pauses listening; **End session** saves a short summary.

Speech-to-text only allows your **target** and **native** languages (never unrestricted auto-detect into other languages).

---

## Speech stack

| Stage | Default | Notes |
|-------|---------|--------|
| STT | faster-whisper | CUDA when usable; else CPU. Bluetooth path can use a larger Whisper size. |
| LLM | Ollama `/api/chat` | Model chosen in the UI from local tags only (`think` disabled for spoken tutoring). |
| TTS | Prefer **piper-tts** (offline) | Fallback: **pyttsx3**. Put Piper `.onnx` voices in `data/piper_voices/`. |

---

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama base URL |
| `BABEL_AGENT_WHISPER` | `base` | faster-whisper size for normal mics |
| `BABEL_AGENT_WHISPER_BT` | `small` | Whisper size when using a Bluetooth mic |
| `BABEL_AGENT_DATA` | `./data` (dev) or OS user data dir (installed) | DB, settings, audio |

Settings (mic, output, talk mode) are stored in `settings.json` under the data directory.

---

## Project layout

```
babel-agent/
  app.py
  run.sh
  requirements.txt
  README.md
  packaging/
    babel-agent.spec
    linux/build_deb.sh
    macos/build_macos.sh
    windows/build_windows.ps1
  data/                 # learner.db, settings, audio, piper voices (dev)
  babel_agent/
    ui.py
    audio_capture.py
    audio_output.py
    ollama_client.py
    stt.py / tts.py
    memory.py / leveling.py
    practice_modes.py / tutor.py
    config.py
```

---

## Troubleshooting

- **“Ollama is not reachable”** — start the Ollama app/service; check `OLLAMA_HOST`.
- **“has no models”** — run `ollama pull <name>` yourself, then Refresh in the app.
- **Mic error / PortAudio (Linux)** — `sudo apt install libportaudio2`.
- **Mic error (macOS)** — `brew install portaudio`; grant Microphone permission to Terminal/the app.
- **Bad transcripts away from the PC** — use the Mic dropdown (Bluetooth headset mic vs laptop); watch the live level while recording. Headset call-mode audio is narrowband.
- **No sound in the headset** — set **Output** to your Bluetooth sink; on Linux `paplay` is used when available.
- **No tutor voice** — install `piper-tts` and place a voice under `data/piper_voices/`, or rely on `pyttsx3`.
- **Python 3.13+ wheel failures** — create the venv with 3.11 or 3.12.
- **Phone call cuts you off early** — silence delay defaults to 3 seconds; speak continuously or pause shorter than that, or switch to Push-to-talk.

---

## License / originality

Original code for this project. Do not copy PolyForm-Noncommercial sources from langteacher into this tree.

> Note: environment variables are now `BABEL_AGENT_*`; the old `LANG_TUTOR_*` names still work as fallbacks inside the app.
