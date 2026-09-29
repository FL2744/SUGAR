#!/bin/zsh
set -euo pipefail
HERE="${0:A:h:h}"
ROOT="${HERE:h}"
BUILD="$HERE/.build-native"
APP="$BUILD/SUGAR.app"
VERSION="$(awk -F'"' '/^version = / {print $2; exit}' "$ROOT/pyproject.toml")"
DMG="$BUILD/SUGAR-$VERSION-unsigned.dmg"
"$HERE/scripts/build_app.sh"
STAGE="$BUILD/dmg-stage"; rm -rf "$STAGE"; mkdir -p "$STAGE"
ditto "$APP" "$STAGE/SUGAR.app"
ln -sfn /Applications "$STAGE/Applications"
hdiutil create -volname SUGAR -srcfolder "$STAGE" -ov -format UDZO "$DMG"
echo "$DMG"
