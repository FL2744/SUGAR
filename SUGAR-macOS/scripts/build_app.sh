#!/bin/zsh
set -euo pipefail
HERE="${0:A:h:h}"
ROOT="${HERE:h}"
BUILD="$HERE/.build-native"
APP="$BUILD/SUGAR.app"
cd "$HERE"
swift build -c release
if [[ ! -x "$BUILD/backend/sugar-bridge" ]]; then
  "$HERE/scripts/build_backend.sh"
fi
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$HERE/.build/release/SUGARMac" "$APP/Contents/MacOS/SUGAR"
cp "$BUILD/backend/sugar-bridge" "$APP/Contents/Resources/sugar-bridge"
cp "$HERE/Resources/Info.plist" "$APP/Contents/Info.plist"
if [[ -f "$ROOT/sugar-logo.png" ]]; then
  ICONSET="$BUILD/SUGAR.iconset"; mkdir -p "$ICONSET"
  for spec in '16 16' '16 32' '32 32' '32 64' '128 128' '128 256' '256 256' '256 512' '512 512' '512 1024'; do
    set -- ${(s: :)spec}; size=$1; pixels=$2
    suffix=""; [[ "$pixels" -gt "$size" ]] && suffix="@2x"
    sips -z "$pixels" "$pixels" "$ROOT/sugar-logo.png" --out "$ICONSET/icon_${size}x${size}${suffix}.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/SUGAR.icns"
fi
chmod +x "$APP/Contents/MacOS/SUGAR" "$APP/Contents/Resources/sugar-bridge"
codesign --force --deep --sign - "$APP"
echo "$APP"
