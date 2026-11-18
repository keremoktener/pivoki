import AppKit

enum PivokiArtwork {
    static let ink = NSColor(srgbRed: 0.125, green: 0.161, blue: 0.129, alpha: 1)
    static func mark(size: CGFloat, happy: Bool = false) -> NSImage {
        if let path = Bundle.main.url(forResource: "Pivoki", withExtension: "png"), let image = NSImage(contentsOf: path) {
            return image
        }
        let image = NSImage(systemSymbolName: "square.3.layers.3d", accessibilityDescription: "Pivoki") ?? NSImage(size: .init(width: size, height: size))
        return image
    }
    static func menuIcon() -> NSImage {
        let image = NSImage(systemSymbolName: "square.3.layers.3d", accessibilityDescription: "Pivoki") ?? mark(size: 18)
        image.isTemplate = true
        return image
    }
}
