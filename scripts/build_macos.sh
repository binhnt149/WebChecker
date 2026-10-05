#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-./scripts/python3.10}"
APP_NAME="SiteSentry Desktop"
DMG_NAME="SiteSentry-Desktop-macOS.dmg"

"$PYTHON_BIN" -m pip install -r requirements.txt -r requirements-build.txt
"$PYTHON_BIN" scripts/make_macos_icon.py

rm -rf build dist
export PYINSTALLER_CONFIG_DIR="$PWD/build/pyinstaller-config"
mkdir -p "$PYINSTALLER_CONFIG_DIR"
"$PYTHON_BIN" -m PyInstaller --noconfirm packaging/sitesentry_macos.spec

if command -v codesign >/dev/null 2>&1; then
  xattr -cr "dist/${APP_NAME}.app" || true
  codesign --force --deep --sign - "dist/${APP_NAME}.app" || true
fi

rm -f "dist/${DMG_NAME}"
hdiutil create \
  -volname "${APP_NAME}" \
  -srcfolder "dist/${APP_NAME}.app" \
  -ov \
  -format UDZO \
  "dist/${DMG_NAME}"

echo "Created dist/${DMG_NAME}"
