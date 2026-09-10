#!/bin/zsh
set -euo pipefail
: "${DEVELOPER_ID_APPLICATION:?Set DEVELOPER_ID_APPLICATION to your Developer ID Application certificate name}"
: "${NOTARY_PROFILE:?Set NOTARY_PROFILE to an xcrun notarytool Keychain profile}"
HERE="${0:A:h:h}"; BUILD="$HERE/.build-native"; APP="$BUILD/SUGAR.app"
"$HERE/scripts/build_app.sh"
codesign --force --options runtime --timestamp --sign "$DEVELOPER_ID_APPLICATION" "$APP/Contents/Resources/sugar-bridge"
codesign --force --options runtime --timestamp --entitlements "$HERE/Resources/SUGAR.entitlements" --sign "$DEVELOPER_ID_APPLICATION" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
ditto -c -k --keepParent "$APP" "$BUILD/SUGAR-notarization.zip"
xcrun notarytool submit "$BUILD/SUGAR-notarization.zip" --keychain-profile "$NOTARY_PROFILE" --wait
xcrun stapler staple "$APP"
STAGE="$BUILD/release-stage"; mkdir -p "$STAGE"; ditto "$APP" "$STAGE/SUGAR.app"; ln -sfn /Applications "$STAGE/Applications"
DMG="$BUILD/SUGAR-1.0.0.dmg"; hdiutil create -volname SUGAR -srcfolder "$STAGE" -ov -format UDZO "$DMG"
codesign --force --timestamp --sign "$DEVELOPER_ID_APPLICATION" "$DMG"
xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
xcrun stapler staple "$DMG"
spctl --assess --type open --context context:primary-signature -v "$DMG"
echo "$DMG"
