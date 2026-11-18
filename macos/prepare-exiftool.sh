#!/bin/bash
# Fetch the upstream Perl utility used by the native metadata editor.
set -euo pipefail
cd "$(dirname "$0")/.."
cache="$PWD/.build/pivoki-tools"
mkdir -p "$cache"
version=13.59
stage=$(mktemp -d "$cache/.exiftool.XXXXXXXX")
trap 'rm -rf "$stage"' EXIT
if [[ ! -x "$cache/ExifTool-$version/exiftool" ]]; then
  curl --fail --location --retry 2 'https://codeload.github.com/exiftool/exiftool/tar.gz/2200871d9cef988051d2a99d67df3bda6cbb30a8' -o "$stage/source.tar.gz"
  checksum=$(shasum -a 256 "$stage/source.tar.gz" | awk '{print $1}')
  [[ "$checksum" == e1e2ad6c6fbf568afee5993ef8b2b91ab013d21698c9304e079e633ad82776f5 ]] || { echo "ExifTool archive checksum mismatch" >&2; exit 1; }
  mkdir "$stage/source" "$stage/tool"
  tar -xzf "$stage/source.tar.gz" --strip-components=1 -C "$stage/source"
  cp -R "$stage/source/exiftool" "$stage/source/lib" "$stage/source/README" "$stage/tool/"
  cp Resources/licenses/ExifTool-LICENSE.txt "$stage/tool/LICENSE"
  mv "$stage/tool" "$cache/ExifTool-$version"
fi
[[ "$(/usr/bin/perl "$cache/ExifTool-$version/exiftool" -config '' -ver)" == "$version" ]]
echo "$cache/ExifTool-$version"
