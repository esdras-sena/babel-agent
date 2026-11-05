#!/usr/bin/env bash
# Launch Babel Agent as a native desktop window (PySide6).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      ver="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
      major="${ver%%.*}"
      minor="${ver#*.}"
      if [[ "$major" -eq 3 && "$minor" -ge 10 && "$minor" -le 12 ]]; then
        PYTHON_BIN="$candidate"
        break
      fi
    fi
  done
fi

if [[ -z "${PYTHON_BIN:-}" ]]; then
  for candidate in python3 python3.13 python3.14; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      echo "Warning: using $PYTHON_BIN — prefer Python 3.10–3.12 for best wheel support."
      break
    fi
  done
fi

if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "Need Python 3.10+. Install one, or set PYTHON_BIN=/path/to/python3.11"
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Creating venv with $PYTHON_BIN ..."
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

# System PortAudio is required by sounddevice (mic capture)
if ! python -c "import sounddevice" 2>/dev/null; then
  echo "sounddevice failed to import. On Debian/Ubuntu install:"
  echo "  sudo apt install libportaudio2 portaudio19-dev"
  exit 1
fi


# faster-whisper / ctranslate2 need libcublas.so.12. Prefer Ollama's bundled
# CUDA 12 libs (or a real toolkit) when the system package is missing.
_cuda_lib_dirs=()
for _d in \
  /usr/local/lib/ollama/cuda_v12 \
  /usr/local/cuda/lib64 \
  /usr/local/cuda-12/lib64
do
  if [[ -d "$_d" ]]; then
    _cuda_lib_dirs+=("$_d")
  fi
done
# Also pick up pip-installed NVIDIA wheels inside the venv, if present.
shopt -s nullglob
for _d in \
  "${ROOT}/.venv/lib"/python*/site-packages/nvidia/cublas/lib \
  "${ROOT}/.venv/lib"/python*/site-packages/nvidia/cuda_runtime/lib \
  "${ROOT}/.venv/lib"/python*/site-packages/nvidia/cudnn/lib
do
  if [[ -d "$_d" ]]; then
    _cuda_lib_dirs+=("$_d")
  fi
done
shopt -u nullglob
if ((${#_cuda_lib_dirs[@]})); then
  _joined="$(IFS=:; echo "${_cuda_lib_dirs[*]}")"
  export LD_LIBRARY_PATH="${_joined}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

mkdir -p data
exec python -m babel_agent
