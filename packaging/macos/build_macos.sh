#!/usr/bin/env bash
# Build a macOS .app (and optional .dmg) with PyInstaller.
# Must be run on macOS.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
VERSION="${VERSION:-0.3.1}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script must run on macOS."
  exit 1
fi

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt pyinstaller
# PortAudio via Homebrew recommended: brew install portaudio

rm -rf dist/BabelAgent dist/BabelAgent.app build
pyinstaller --noconfirm --clean \
  --windowed \
  --name BabelAgent \
  --hidden-import=babel_agent.ui \
  --hidden-import=PySide6.QtMultimedia \
  app.py

# Optional DMG
if command -v hdiutil >/dev/null 2>&1; then
  DMG="dist/BabelAgent-${VERSION}-macos.dmg"
  rm -f "$DMG"
  hdiutil create -volname "Babel Agent" -srcfolder dist/BabelAgent.app -ov -format UDZO "$DMG"
  echo "DMG: $DMG"
fi

echo "App: dist/BabelAgent.app"
echo "Open with: open dist/BabelAgent.app"
