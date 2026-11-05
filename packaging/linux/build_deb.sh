#!/usr/bin/env bash
# Build BabelAgent with PyInstaller and package a .deb
# Run from repo root:  ./packaging/linux/build_deb.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
VERSION="${VERSION:-0.3.1}"
ARCH="${ARCH:-amd64}"
DIST="$ROOT/dist"
BUILD_ROOT="$DIST/deb-root"
PKG_NAME="babel-agent"
DEB_NAME="${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo "==> Repo: $ROOT"
echo "==> Version: $VERSION"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -U pip
pip install -q -r requirements.txt pyinstaller

echo "==> PyInstaller (onedir)…"
rm -rf "$DIST/BabelAgent" "$DIST/BabelAgent.bin" build
pyinstaller --noconfirm --clean packaging/babel-agent.spec

APP_BUNDLE="$DIST/BabelAgent"
if [[ ! -x "$APP_BUNDLE/BabelAgent" ]]; then
  echo "PyInstaller did not produce $APP_BUNDLE/BabelAgent"
  ls -la "$DIST" || true
  exit 1
fi

echo "==> Assembling Debian package tree…"
rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT/DEBIAN"
mkdir -p "$BUILD_ROOT/opt/babel-agent"
mkdir -p "$BUILD_ROOT/usr/bin"
mkdir -p "$BUILD_ROOT/usr/share/applications"
mkdir -p "$BUILD_ROOT/usr/share/doc/$PKG_NAME"

# Copy onedir payload
cp -a "$APP_BUNDLE/." "$BUILD_ROOT/opt/babel-agent/"

# Wrapper
install -m 0755 packaging/linux/babel-agent-wrapper.sh \
  "$BUILD_ROOT/usr/bin/babel-agent"

# Desktop entry
install -m 0644 packaging/linux/babel-agent.desktop \
  "$BUILD_ROOT/usr/share/applications/babel-agent.desktop"

# App icon (hicolor + pixmaps for desktop entry)
mkdir -p "$BUILD_ROOT/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$BUILD_ROOT/usr/share/pixmaps"
if [[ -f assets/icon.png ]]; then
  install -m 0644 assets/icon.png \
    "$BUILD_ROOT/usr/share/icons/hicolor/256x256/apps/babel-agent.png"
  install -m 0644 assets/icon.png \
    "$BUILD_ROOT/usr/share/pixmaps/babel-agent.png"
  # also keep assets next to the app binary for the window icon
  mkdir -p "$BUILD_ROOT/opt/babel-agent/assets"
  install -m 0644 assets/icon.png "$BUILD_ROOT/opt/babel-agent/assets/icon.png"
  install -m 0644 assets/logo.png "$BUILD_ROOT/opt/babel-agent/assets/logo.png"
fi


# Docs
cp README.md "$BUILD_ROOT/usr/share/doc/$PKG_NAME/"
cat > "$BUILD_ROOT/usr/share/doc/$PKG_NAME/copyright" << COPYRIGHT
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: babel-agent
Copyright: 2026 Babel Agent contributors
License: MIT-like / original project license as distributed with the source
COPYRIGHT

INSTALLED_SIZE="$(du -sk "$BUILD_ROOT/opt" "$BUILD_ROOT/usr" | awk '{s+=$1} END {print s}')"

cat > "$BUILD_ROOT/DEBIAN/control" << CONTROL
Package: $PKG_NAME
Version: $VERSION
Section: education
Priority: optional
Architecture: $ARCH
Installed-Size: $INSTALLED_SIZE
Depends: libportaudio2, libasound2t64 | libasound2
Maintainer: Babel Agent <noreply@localhost>
Description: Local AI language-learning desktop tutor (Ollama + voice)
 Native desktop app: speak → STT → local Ollama LLM → TTS.
 Detects models already installed via Ollama; never pulls or installs models.
 Learner memory (SQLite) and automatic CEFR leveling A1–C2.
CONTROL

cat > "$BUILD_ROOT/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
set -e
# Refresh desktop database if available
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
exit 0
POSTINST
chmod 0755 "$BUILD_ROOT/DEBIAN/postinst"

echo "==> dpkg-deb…"
mkdir -p "$DIST"
dpkg-deb --root-owner-group --build "$BUILD_ROOT" "$DIST/$DEB_NAME"

echo
echo "Built: $DIST/$DEB_NAME"
echo "Binary onedir: $APP_BUNDLE/BabelAgent"
echo
echo "Install with:"
echo "  sudo apt install ./dist/$DEB_NAME"
echo "  # or: sudo dpkg -i ./dist/$DEB_NAME && sudo apt -f install"
echo "Then run: babel-agent"
