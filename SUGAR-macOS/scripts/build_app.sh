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
export MACOSX_DEPLOYMENT_TARGET=13.0
swift build -c release
# Always rebuild: cached backends can contain a newer Python runtime.
"$HERE/scripts/build_backend.sh"
ARCH="$(uname -m)"
"$BUILD/backend-venv/bin/python" "$HERE/scripts/check_compatibility.py" \
  "$HERE/.build/release/SUGARMac" --arch "$ARCH"
"$BUILD/backend-venv/bin/python" "$HERE/scripts/check_compatibility.py" \
  "$BUILD/backend/sugar-bridge" --archive --arch "$ARCH"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$APP/Contents/Resources/Samples"
cp "$HERE/.build/release/SUGARMac" "$APP/Contents/MacOS/SUGAR"
cp "$BUILD/backend/sugar-bridge" "$APP/Contents/Resources/sugar-bridge"
cp "$HERE/Resources/Info.plist" "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$APP/Contents/Info.plist"

# Bundle a credential-free classroom path so a new user can immediately inspect
# representative SUGAR outputs and run map/report workflows without an API key.
cp "$ROOT/examples/example-spreadsheet.xlsx" "$APP/Contents/Resources/Samples/example-spreadsheet.xlsx"
cp "$ROOT/examples/example-map.html" "$APP/Contents/Resources/Samples/example-map.html"
cp "$ROOT/examples/example-analysis.pdf" "$APP/Contents/Resources/Samples/example-analysis.pdf"
cp "$ROOT/docs/classroom-preview.md" "$APP/Contents/Resources/Samples/classroom-preview.md"

GIT_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
BUILT_AT_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
cat > "$APP/Contents/Resources/build-info.json" <<EOF
{
  "product": "SUGAR",
  "version": "$VERSION",
  "git_commit": "$GIT_COMMIT",
  "built_at_utc": "$BUILT_AT_UTC",
  "architecture": "$ARCH",
  "bridge_protocol": 3,
  "runtime": "bundled",
  "ordinary_users_need_python": false
}
EOF

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

echo "SUGAR $VERSION ($GIT_COMMIT) architecture check: app=$APP_ARCHS backend=$BACKEND_ARCHS"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
echo "$APP"
