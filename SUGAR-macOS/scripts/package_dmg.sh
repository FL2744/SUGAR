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

# Once SUGAR.app has passed its packaged smoke tests, build intermediates are
# disposable. Clear them before imaging so hosted runners retain enough free
# disk for hdiutil's temporary compression work.
if [[ "${SUGAR_SKIP_APP_BUILD:-0}" == "1" ]]; then
  rm -rf \
    "$BUILD/backend-venv" \
    "$BUILD/backend" \
    "$BUILD/pyinstaller" \
    "$HERE/.build"
fi

# Package the already validated application bundle directly. The previous
# staging step made a second full copy of SUGAR.app before hdiutil made its own
# image copy, which could exhaust GitHub's hosted macOS runner. A classroom
# preview does not need a decorative /Applications symlink inside the image.
rm -f "$DMG"
hdiutil create \
  -volname SUGAR \
  -srcfolder "$APP" \
  -ov \
  -format UDZO \
  "$DMG"

# Verify the disk image wrapper itself. The contained application has already
# passed architecture, bundled-backend, analysis, sample, and codesign checks.
hdiutil verify "$DMG"
echo "$DMG"
