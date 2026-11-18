#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
configuration=${1:-release}
case "$configuration" in debug|release) ;; *) echo "Usage: macos/build-app.sh [debug|release]" >&2; exit 64;; esac
engine_dir=${PIVOKI_ENGINE_DIR:-"$PWD/dist/engine/pivoki-engine"}
if [[ ! -x "$engine_dir/pivoki-engine" ]]; then
  echo "Build the engine first, or set PIVOKI_ENGINE_DIR to its packaged directory." >&2
  exit 1
fi
scratch=${PIVOKI_SWIFT_SCRATCH:-"$PWD/.build/native-bundle"}
swift build --scratch-path "$scratch" -c "$configuration" -j "${PIVOKI_BUILD_JOBS:-6}" -Xswiftc -file-prefix-map -Xswiftc "$PWD=/pivoki"
bin=$(swift build --scratch-path "$scratch" -c "$configuration" --show-bin-path)
output=${PIVOKI_APP_OUTPUT:-"$PWD/dist/Pivoki.app"}
mkdir -p "$(dirname "$output")"
if [[ -e "$output" ]]; then
  current_id=$(plutil -extract CFBundleIdentifier raw -o - "$output/Contents/Info.plist" 2>/dev/null || true)
  [[ "$current_id" == "app.pivoki.desktop" ]] || { echo "Output belongs to another application: $output" >&2; exit 1; }
fi
stage=$(mktemp -d "$(dirname "$output")/.pivoki-mac.XXXXXXXX")
trap 'rm -rf "$stage"' EXIT
bundle="$stage/Pivoki.app"
contents="$bundle/Contents"
mkdir -p "$contents/MacOS" "$contents/Resources"
exiftool_dir=$(macos/prepare-exiftool.sh)
mkdir -p "$contents/Resources/Tools"
ditto "$exiftool_dir" "$contents/Resources/Tools/ExifTool"
cp Resources/Info.plist "$contents/Info.plist"
cp "$bin/Pivoki" "$bin/pivoki-cli" "$contents/MacOS/"
ditto "$bin/Pivoki_PivokiCore.bundle" "$contents/Resources/Pivoki_PivokiCore.bundle"
ditto "$engine_dir" "$contents/Resources/Engine"
ditto Resources/Localizations "$contents/Resources"
ditto Resources/licenses "$contents/Resources/licenses"
ditto Resources/Sounds "$contents/Resources/Sounds"
cp Resources/*.js Resources/FeatureCatalog.json Resources/THIRD-PARTY-NOTICES.txt Resources/LICENSE-Nashi.txt branding/Pivoki.icns branding/Pivoki.png "$contents/Resources/"
cp LICENSE "$contents/Resources/Pivoki-LICENSE.txt"
codesign --force --sign - "$bundle"
codesign --verify --strict "$bundle"
if [[ -e "$output" ]]; then mv "$output" "$stage/previous.app"; fi
if ! mv "$bundle" "$output"; then
  if [[ -d "$stage/previous.app" ]]; then mv "$stage/previous.app" "$output"; fi
  exit 1
fi
echo "$output"
