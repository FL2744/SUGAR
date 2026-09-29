#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h:h:h}"
BUNDLE="$ROOT/SUGAR-Desktop/src-tauri/target/release/bundle/dmg"
if [[ ! -d "$BUNDLE" ]] || [[ -z "$(find "$BUNDLE" -maxdepth 1 -type f -name '*.dmg' -print -quit)" ]]; then
  exec "$ROOT/SUGAR-Desktop/scripts/build-macos.sh"
fi
find "$BUNDLE" -maxdepth 1 -type f -name '*.dmg' -print
