#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h:h:h}"
exec "$ROOT/SUGAR-Desktop/scripts/build-macos.sh"
