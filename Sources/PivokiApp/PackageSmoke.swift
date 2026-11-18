import AppKit
import PivokiCore
import SwiftUI

/// Uses the same model, RPC, views and library actions as a normal package window.
@MainActor final class PackageSmoke: NSObject, NSApplicationDelegate {
    let output: URL
    private var window: NSWindow?
    init(output: URL) { self.output = output }
    func applicationDidFinishLaunching(_ notification: Notification) {
        Task {
            do { try await exercise(); print("PACKAGE PASS"); exit(0) }
            catch { fputs(error.localizedDescription + "\n", stderr); exit(1) }
        }
    }
    private func check(_ condition: Bool, _ message: String) throws {
        if !condition { throw PivokiError.failed(message) }
    }
    private func exercise() async throws {
        let fm = FileManager.default
        try fm.createDirectory(at: output, withIntermediateDirectories: true)
        let root = fm.temporaryDirectory.appendingPathComponent("pivoki-native-smoke-" + UUID().uuidString, isDirectory: true)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }
        setenv("PIVOKI_DATA_DIR", root.appendingPathComponent("state").path, 1)
        let suite = "Pivoki.PackageSmoke." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let state = AppState(defaults: defaults), model = PackageWorkspace(state: state)
        guard let sample = Bundle.main.url(forResource: "Pivoki", withExtension: "png") else { throw PivokiError.failed("Run this check from the assembled Pivoki.app.") }
        let source = try Data(contentsOf: sample)
        let input = root.appendingPathComponent("Görseller"), destination = root.appendingPathComponent("Çıktı")
        for dir in [input, destination] { try fm.createDirectory(at: dir, withIntermediateDirectories: false) }
        for n in 1...20 { try source.write(to: input.appendingPathComponent("Örnek \(n).png")) }
        try Data("Other".utf8).write(to: input.appendingPathComponent("notes.txt"))
        await model.load()
        try check(!model.packages.isEmpty, model.message)
        let example = OutputPackage(name: "Fotoğraf seti", outputs: [
            .init(format: "webp", maxEdge: 1600, relativeDir: "web"),
            .init(format: "jpg", maxEdge: 400, relativeDir: "small")
        ])
        let createError = await model.save(example)
        try check(createError == nil && model.selected?.revision == 1, createError ?? "Package was not saved.")
        guard var revised = model.selected else { throw PivokiError.failed("The saved package is missing.") }
        revised.name += " 2"
        let editError = await model.save(revised)
        try check(editError == nil && model.selected?.revision == 2, editError ?? "Revision was not incremented.")
        model.inputs = [input]; model.destination = destination
        await model.plan()
        try check(model.readyRows == 40 && model.preview?.skipped?.count == 1, "Plan expected 40 outputs and one excluded text file. " + model.message)
        try capture(PackageView(model: model, state: state), file: "output-plan.png")
        guard let originalDestination = model.preview?.directory else { throw PivokiError.failed("Missing planned destination.") }
        let competitor = URL(fileURLWithPath: originalDestination).appendingPathComponent("existing.txt")
        try fm.createDirectory(at: competitor.deletingLastPathComponent(), withIntermediateDirectories: false)
        try Data("reserved".utf8).write(to: competitor)
        await model.run()
        try check(model.result == nil && model.readyRows == 40 && model.previousPaths.count == 40 && state.history.isEmpty,
                  "The late conflict did not stop for a revised plan: " + model.message)
        try capture(PackageView(model: model, state: state), file: "revised-plan.png")
        await model.run()
        let competingBytes = try Data(contentsOf: competitor)
        try check(competingBytes == Data("reserved".utf8), "The competing file changed.")
        guard let paths = model.result?.paths, paths.count == 40 else { throw PivokiError.failed("Native package failed. " + model.message) }
        for path in paths {
            let image = try ImageEngine.load(URL(fileURLWithPath: path)), edge = max(image.width, image.height)
            try check(edge == (path.hasSuffix(".jpg") ? 400 : 1024), "Unexpected image dimensions: " + path)
        }
        try check(state.history.count == 1 && state.history[0].outputs.count == 40, "Expected one library job.")
        let original = try Data(contentsOf: input.appendingPathComponent("Örnek 1.png"))
        try check(original == source, "Source bytes changed.")
        await state.removeRecord(state.history[0])
        try check(state.history.isEmpty && paths.allSatisfy(fm.fileExists(atPath:)), "Removing a library job affected its files.")
        await model.deleteSelected()
        try check(!model.packages.contains { $0.id == revised.id }, "Deleted package is still active.")
        try capture(PackageView(model: model, state: state), file: "output-packages.png")
    }
    private func capture<V: View>(_ view: V, file: String) throws {
        let frame = NSRect(x: 0, y: 0, width: 760, height: 720)
        let window = NSWindow(contentRect: frame, styleMask: [.titled], backing: .buffered, defer: false)
        let host = NSHostingView(rootView: view.pivokiLanguage())
        window.contentView = host; window.center(); window.orderFront(nil)
        self.window = window
        host.layoutSubtreeIfNeeded()
        guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { throw PivokiError.failed("Window capture failed.") }
        host.cacheDisplay(in: host.bounds, to: bitmap)
        guard let png = bitmap.representation(using: .png, properties: [:]) else { throw PivokiError.failed("PNG capture failed.") }
        try png.write(to: output.appendingPathComponent(file))
        window.orderOut(nil)
    }
}
