#!/bin/zsh
set -euo pipefail
DESKTOP="${0:A:h:h}"
ROOT="${DESKTOP:h}"
HOST="$(rustc -vV | sed -n 's/^host: //p')"
case "$HOST" in
  aarch64-apple-darwin|x86_64-apple-darwin) ;;
  *) echo "Expected an Apple Silicon or Intel macOS Rust target, received: $HOST" >&2; exit 1 ;;
esac
PYTHON="${PYTHON:-python3.12}"
UPDATER_CONFIG="$DESKTOP/src-tauri/.updater-build.json"
"$PYTHON" "$ROOT/tools/release_tools.py" updater-config --output "$UPDATER_CONFIG"
ARCH="$($PYTHON -c 'import platform; print(platform.machine())')"
case "$HOST:$ARCH" in
  aarch64-apple-darwin:arm64|x86_64-apple-darwin:x86_64) ;;
  *) echo "Python architecture ($ARCH) must match the Rust target ($HOST)." >&2; exit 1 ;;
esac
"$DESKTOP/scripts/build-macos-backend.sh"
BRIDGE="$DESKTOP/.build-macos/backend/sugar-bridge"
mkdir -p "$DESKTOP/src-tauri/binaries"
cp "$BRIDGE" "$DESKTOP/src-tauri/binaries/sugar-bridge-$HOST"
cd "$DESKTOP"
if [[ -n "${CI:-}" || ! -d node_modules ]]; then npm ci; fi
npm run tauri -- build --config "$UPDATER_CONFIG"
echo "Unified SUGAR desktop package created under $DESKTOP/src-tauri/target/release/bundle"
