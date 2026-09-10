#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h:h:h}"
BUILD="$ROOT/SUGAR-macOS/.build-native"
PYTHON="${PYTHON:-python3}"
mkdir -p "$BUILD"
"$PYTHON" -m venv "$BUILD/backend-venv"
"$BUILD/backend-venv/bin/python" -m pip install -U pip
"$BUILD/backend-venv/bin/python" -m pip install "$ROOT[macos]"
"$BUILD/backend-venv/bin/pyinstaller" --noconfirm --clean --onefile \
  --name sugar-bridge --distpath "$BUILD/backend" --workpath "$BUILD/pyinstaller" \
  --specpath "$BUILD" --collect-all matplotlib --collect-all folium \
  --hidden-import openpyxl --hidden-import reportlab --hidden-import docx \
  "$ROOT/sugar_bridge.py"
"$BUILD/backend/sugar-bridge" diagnostics
file "$BUILD/backend/sugar-bridge"
echo "$BUILD/backend/sugar-bridge"
