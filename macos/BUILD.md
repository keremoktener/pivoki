# Build Pivoki on macOS

The complete app with RAW support requires macOS 14 or later. Install Xcode with Swift 6 and a Python 3.11 or 3.12 distribution that includes Tk. From the repository root, run the following command.

```sh
./macos/build-from-source.sh
```

The script creates a private Python environment under `.build`, installs the image and document engines, verifies the pinned ExifTool download, builds the Swift app and signs the result locally. To select a particular interpreter, set `PIVOKI_PYTHON` to its absolute executable path. The initial build downloads dependencies. Local file conversions work offline.

Open `dist/Pivoki.app` in Finder or run `open dist/Pivoki.app`. You can move the entire app to your Applications folder. This build targets the architecture of the Mac that compiled it. The local signature is suitable for running your own build. A public notarized binary needs a Developer ID release process.

## First package

1. Open **Output packages** on Home.
2. Choose **Mağaza görselleri**. Add images or a folder and select the output location. Enable subfolders if needed.
3. Preview the plan to see every destination and any skipped input.
4. Choose **Create outputs**. Open the resulting folder or revisit the job in the Library.

For a single conversion, drop a file on Home or select the built-in sample. The built-in image package works without installing the optional Office and video tool groups.

## Command line

The native CLI lives in the app bundle. Replace the sample input and destination with local paths.

```sh
cli="dist/Pivoki.app/Contents/MacOS/pivoki-cli"
"$cli" catalog
"$cli" package run 4c951577-984b-43a3-b90d-d640668837db \
  --revision 1 --input photo.png --out Delivery \
  --on-conflict keep-both --dry-run --json
```

Remove `--dry-run` to publish the files. For direct access to the shared engine, use `dist/engine/pivoki-engine/pivoki-engine`. The `studio` command opens editors, QR tools and folder rules. Folder rules run while Pivoki is open and only after you explicitly enable them.

## Optional engines

Media editing in Studio uses local `ffmpeg` and `ffprobe`. PDF pages to SVG uses `pdftocairo`. PDF/A-2b requires Ghostscript (`gs`), the `verapdf` CLI and Java. Install these tools separately and make them discoverable on the app's PATH. On macOS Studio also checks `/opt/homebrew/bin` and `/usr/local/bin`. RAW development is included in the full build. Compatibility depends on the camera and LibRaw version.

## Development checks

```sh
.build/pivoki-python/bin/python -m pip install pytest
.build/pivoki-python/bin/python -m pytest -q engine/tests studio/tests
swift test
```

The full native suite includes optional codec and Office integration cases. Some tests exercise installed third-party tools. To run engine tests against a disposable state directory, set `PIVOKI_DATA_DIR`. The default engine database is under `~/Library/Application Support/Pivoki/Engine`.
