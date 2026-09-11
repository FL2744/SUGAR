#!/bin/zsh
set -euo pipefail
HERE="${0:A:h:h}"
ROOT="${HERE:h}"
BUILD="$HERE/.build-native"
APP="$BUILD/SUGAR.app"
VERSION="$(awk -F'"' '/^version = / {print $2; exit}' "$ROOT/pyproject.toml")"
if [[ -z "$VERSION" ]]; then
  echo "Could not determine SUGAR version from pyproject.toml" >&2
  exit 1
fi
cd "$HERE"
swift build -c release
if [[ ! -x "$BUILD/backend/sugar-bridge" ]]; then
  "$HERE/scripts/build_backend.sh"
fi
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$HERE/.build/release/SUGARMac" "$APP/Contents/MacOS/SUGAR"
cp "$BUILD/backend/sugar-bridge" "$APP/Contents/Resources/sugar-bridge"
cp "$HERE/Resources/Info.plist" "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$APP/Contents/Info.plist"

if [[ -f "$ROOT/sugar-logo.png" ]]; then
  ICONSET="$BUILD/SUGAR.iconset"; rm -rf "$ICONSET"; mkdir -p "$ICONSET"
  for spec in '16 16' '16 32' '32 32' '32 64' '128 128' '128 256' '256 256' '256 512' '512 512' '512 1024'; do
    set -- ${(s: :)spec}; size=$1; pixels=$2
    suffix=""; [[ "$pixels" -gt "$size" ]] && suffix="@2x"
    sips -z "$pixels" "$pixels" "$ROOT/sugar-logo.png" --out "$ICONSET/icon_${size}x${size}${suffix}.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/SUGAR.icns"
fi

chmod +x "$APP/Contents/MacOS/SUGAR" "$APP/Contents/Resources/sugar-bridge"
APP_ARCHS="$(lipo -archs "$APP/Contents/MacOS/SUGAR")"
BACKEND_ARCHS="$(lipo -archs "$APP/Contents/Resources/sugar-bridge" 2>/dev/null || true)"
if [[ -z "$BACKEND_ARCHS" ]]; then
  echo "Could not determine bundled backend architecture." >&2
  file "$APP/Contents/Resources/sugar-bridge" >&2
  exit 1
fi
for arch in ${(s: :)APP_ARCHS}; do
  if [[ " $BACKEND_ARCHS " != *" $arch "* ]]; then
    echo "Architecture mismatch: app=$APP_ARCHS backend=$BACKEND_ARCHS" >&2
    exit 1
  fi
done

echo "SUGAR $VERSION architecture check: app=$APP_ARCHS backend=$BACKEND_ARCHS"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
echo "$APP"
