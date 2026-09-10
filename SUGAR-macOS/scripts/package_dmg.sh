#!/bin/zsh
set -euo pipefail
HERE="${0:A:h:h}"
BUILD="$HERE/.build-native"
APP="$BUILD/SUGAR.app"
DMG="$BUILD/SUGAR-1.0.0-unsigned.dmg"
[[ -d "$APP" ]] || "$HERE/scripts/build_app.sh"
STAGE="$BUILD/dmg-stage"; mkdir -p "$STAGE"
ditto "$APP" "$STAGE/SUGAR.app"
ln -sfn /Applications "$STAGE/Applications"
hdiutil create -volname SUGAR -srcfolder "$STAGE" -ov -format UDZO "$DMG"
echo "$DMG"
