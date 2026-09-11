#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h:h:h}"
BUILD="$ROOT/SUGAR-macOS/.build-native"
PYTHON="${PYTHON:-python3.12}"
export MACOSX_DEPLOYMENT_TARGET=13.0
"$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12), "Use Python 3.12 built for macOS 13 or earlier"'
ARCH="$("$PYTHON" -c 'import platform; print(platform.machine())')"
mkdir -p "$BUILD"
"$PYTHON" -m venv --clear "$BUILD/backend-venv"
"$BUILD/backend-venv/bin/python" -m pip install -U pip pyinstaller
# Select the older-macOS wheel explicitly; pip otherwise prefers macOS 14's
# Accelerate-backed NumPy wheel when building on a newer host.
WHEELS="$(mktemp -d "$BUILD/numpy-wheels.XXXXXX")"
trap 'rm -rf "$WHEELS"' EXIT
"$BUILD/backend-venv/bin/python" -m pip download --only-binary=:all: --no-deps \
  --platform "macosx_13_0_${ARCH}" --dest "$WHEELS" 'numpy==2.2.6'
"$BUILD/backend-venv/bin/python" -m pip install "$WHEELS"/numpy-*.whl
"$BUILD/backend-venv/bin/python" -m pip install "${ROOT}[macos]" -c "$ROOT/SUGAR-macOS/constraints-macos.txt"
"$BUILD/backend-venv/bin/pyinstaller" --noconfirm --clean --onefile \
  --name sugar-bridge --distpath "$BUILD/backend" --workpath "$BUILD/pyinstaller" \
  --specpath "$BUILD" --collect-all matplotlib --collect-all folium --collect-all docx \
  --hidden-import openpyxl --hidden-import reportlab --hidden-import docx \
  "$ROOT/sugar_bridge.py"
"$BUILD/backend-venv/bin/python" "$ROOT/SUGAR-macOS/scripts/check_compatibility.py" \
  "$BUILD/backend/sugar-bridge" --archive --arch "$ARCH"
"$BUILD/backend-venv/bin/python" "$ROOT/SUGAR-macOS/scripts/check_word_templates.py" \
  "$BUILD/backend/sugar-bridge"
"$BUILD/backend/sugar-bridge" diagnostics
file "$BUILD/backend/sugar-bridge"
echo "$BUILD/backend/sugar-bridge"
