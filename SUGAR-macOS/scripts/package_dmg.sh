#!/bin/zsh
set -euo pipefail
HERE="${0:A:h:h}"
ROOT="${HERE:h}"
BUILD="$HERE/.build-native"
APP="$BUILD/SUGAR.app"
VERSION="$(awk -F'"' '/^version = / {print $2; exit}' "$ROOT/pyproject.toml")"
DMG="$BUILD/SUGAR-$VERSION-unsigned.dmg"

if [[ "${SUGAR_SKIP_APP_BUILD:-0}" != "1" ]]; then
  "$HERE/scripts/build_app.sh"
fi
if [[ ! -d "$APP" ]]; then
  echo "Packaged app not found at $APP" >&2
  exit 1
fi

# CI builds the frozen backend in a temporary virtual environment and leaves
# several large PyInstaller/Swift intermediate trees behind. Once SUGAR.app has
# passed its packaged smoke tests those intermediates are no longer needed to
# create the DMG, and retaining them can exhaust the hosted runner's disk while
# hdiutil duplicates/compresses the application. Keep the finished app itself.
if [[ "${SUGAR_SKIP_APP_BUILD:-0}" == "1" ]]; then
  rm -rf \
    "$BUILD/backend-venv" \
    "$BUILD/backend" \
    "$BUILD/pyinstaller" \
    "$HERE/.build"
fi

STAGE="$BUILD/dmg-stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/SUGAR.app"
ln -sfn /Applications "$STAGE/Applications"
hdiutil create -volname SUGAR -srcfolder "$STAGE" -ov -format UDZO "$DMG"
echo "$DMG"
