# Pivoki

Pivoki is a local file converter for macOS and Windows. Its first workflow is for people who prepare the same photos for different destinations. Save a package once, preview the exact output paths, then make every version in one run.

For example, the **Mağaza görselleri** package takes 20 product photos and prepares up to 40 files. Each original produces a WebP up to 1600 px wide or tall and a JPEG thumbnail up to 400 px. Small images keep their original dimensions.

## Development

The desktop applications build on the native SwiftUI/AppKit and WPF code of [Nashi](https://github.com/orkunisitmak/nashi-app/tree/855e2bebebc17e29bf4aa79620e35954283d35ae). Pivoki has its own local data and application identity. The shared package engine handles planning, conversion, publication and job history.

Development and platform acceptance are in progress. Build instructions and verified features are added as each component lands.

## License

Original Pivoki material is licensed for personal, noncommercial use. Selling or sublicensing it is prohibited. The Nashi portions retain their original MIT license, and third-party components retain their own licenses. See the [license terms](LICENSE).
