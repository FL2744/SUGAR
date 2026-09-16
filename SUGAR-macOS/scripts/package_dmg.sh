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
    "$HERE/.build" \
    "$HOME/Library/Caches/pip" \
    "$HOME/Library/Caches/org.swift.swiftpm" \
    "$HOME/Library/Developer/Xcode/DerivedData"

  # GitHub's hosted macOS image carries simulator runtimes that are irrelevant
  # after the application has already been built, smoke-tested, and codesign-
  # verified. They consume several GB that hdiutil may otherwise need while it
  # constructs a compressed image. This cleanup is CI-only and never runs on a
  # developer machine.
  if [[ "${CI:-}" == "true" ]]; then
    sudo rm -rf /Library/Developer/CoreSimulator/Profiles/Runtimes/* 2>/dev/null || true
    sudo rm -rf /Library/Developer/CoreSimulator/Caches/* 2>/dev/null || true
    sudo rm -rf /Library/Developer/CoreSimulator/Volumes/* 2>/dev/null || true

    available_kb="$(df -Pk / | awk 'NR==2 {print $4}')"
    if [[ "$available_kb" =~ '^[0-9]+$' ]] && (( available_kb < 6291456 )); then
      # Xcode is no longer required at this point; hdiutil/codesign are macOS
      # system tools. Remove hosted Xcode only as a last-resort space recovery.
      sudo rm -rf /Applications/Xcode*.app 2>/dev/null || true
    fi
  fi
fi

df -h /

# Package the already validated application bundle directly, avoiding an extra
# full staging copy of SUGAR.app.
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
