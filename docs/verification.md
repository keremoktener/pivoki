# Desktop verification

Pivoki 0.1.0 is a development build. The first delivery centers on preparing image packages locally and reviewing their paths before writing. This record distinguishes reproducible checks from outstanding platform acceptance.

| Area | Evidence |
| --- | --- |
| Image packages and folders | The native Mac package smoke test creates and revises a package, plans 20 source images and an excluded text file, introduces a destination conflict, obtains a revised plan, then reads back 40 real WebP/JPEG outputs. Removing the job from history preserves the files. |
| File integrity | Engine regression tests cover identical basenames, Unicode paths, cancellation, changed source contents, concurrent execution, a late competing directory, interrupted publication and recovery. |
| Studio | Tests cover a UTF-8 QR round trip, an alpha-preserving seven-layer ICO, connected background removal, captions, signed-PDF routing, ZIP contents, selected-page PDF watermarks and vector SVG exports. Video checks inspect silent H.264 output, mask time boundaries and the side-by-side preview. |
| PDF/A | A generated document passed the independent veraPDF 1.30.4 flavour 2b check with Ghostscript 10.08.0. Invalid input was rejected before publication. These executables are optional external tools. |
| RAW | On Apple Silicon the LibRaw 0.22.2 adapter decoded the rawpy test corpus’s Canon 40D sRAW and Nikon NEF samples at 1944 × 1296 and 4284 × 2844 respectively. Apple ImageIO read the resulting PNGs and both source digests were unchanged. The eight-family camera matrix remains open. |
| UYAP | Generated UDF fixtures exercise Turkish text, UTF-16 offsets, tables, lists, signature parts and PDF/DOCX copies. Representative documents and comparison in the official editor are pending. DOCX-to-UDF authoring is deferred. |
| Windows | The Windows CI job exercises the core, builds WPF, and opens the actual package dialog with a frozen engine to approve and reapprove a plan. The source includes publisher-signing scripts. Authenticode distribution requires a publisher identity. |
| Linux | Ubuntu 24.04 ARM64 tests under Xvfb/X11 and Weston/XWayland exercise real file drops and file selection. The Linux desktop exposes the available session capabilities. |

The native desktop UI supports English and Turkish, with French on Mac. Studio supports switching the control labels among the three languages while preserving the draft. Some Studio diagnostics and confirmations still use Turkish.

Physical Finder/Explorer gesture acceptance with Photoshop and a full-screen game, VoiceOver/Narrator user trials, measured frame-time percentiles and the complete camera matrix require further testing. macOS application updates and notarized public distribution require Pivoki’s own release channel and signing configuration.

The rawpy sample files are used only for verification and are not included in the repository. [Upstream test corpus](https://github.com/letmaik/rawpy/tree/main/test)

## Repeat the checks

Run the shared suites from an environment with both Python packages installed. Poppler, FFmpeg, Ghostscript and veraPDF enable their corresponding integration tests.

```sh
python -m pytest -q engine/tests studio/tests
```

After building the Mac application, use fresh temporary paths for its native package-flow check.

```sh
work=$(mktemp -d)
PIVOKI_DATA_DIR="$work/profile" dist/Pivoki.app/Contents/MacOS/Pivoki --package-smoke "$work/results"
```

Build and platform-specific verification commands are in the [macOS build guide](../macos/BUILD.md), [Windows guide](../windows/README.md) and [Linux guide](../linux/README.md).
