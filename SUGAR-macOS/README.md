# SUGAR for macOS

This directory contains the native SwiftUI distribution of SUGAR. The app stores
credentials in macOS Keychain and bundles the Python search, map, and analysis
engine so recipients do not install Python or use Terminal.

## Build an unsigned test release

```bash
./scripts/build_app.sh
./scripts/package_dmg.sh
```

Outputs are written under `.build-native/`. The unsigned DMG is suitable for
local testing but Gatekeeper will warn other users.

## Create a signed and notarized public release

Public distribution requires Apple Developer Program membership, full Xcode,
a `Developer ID Application` certificate installed in Keychain, and a notarytool
profile. After installing Xcode, select it with `sudo xcode-select -s
/Applications/Xcode.app/Contents/Developer` and accept its license.

Store notarization credentials once:

```bash
xcrun notarytool store-credentials SUGAR-notary \
  --apple-id "YOUR_APPLE_ID" \
  --team-id "YOUR_TEAM_ID" \
  --password "APP_SPECIFIC_PASSWORD"
```

Then build, sign, notarize, staple, and verify the release:

```bash
export DEVELOPER_ID_APPLICATION="Developer ID Application: Your Name (TEAMID)"
export NOTARY_PROFILE="SUGAR-notary"
./scripts/release_notarized.sh
```

Never place Apple, X, OpenAI, ARC, Bluesky, or Mastodon credentials in this
repository. Runtime service credentials belong in the app's Settings screen and
are stored in macOS Keychain.
