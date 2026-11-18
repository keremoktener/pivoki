import AppKit
import ApplicationServices
import PivokiCore
import SwiftUI
import UniformTypeIdentifiers

private struct WheelProfile: Codable, Identifiable {
    var id = UUID()
    var name: String
    var hidden = Set<String>()
    var pins = Set<String>()
}

@MainActor final class WheelPreferences: ObservableObject {
    static let shared = WheelPreferences()
    @Published private var profiles: [WheelProfile]
    @Published private(set) var currentID: UUID
    private let defaults = UserDefaults.standard
    init() {
        let saved = defaults.data(forKey: "wheelProfiles").flatMap { try? JSONDecoder().decode([WheelProfile].self, from: $0) }
        let profiles = saved?.isEmpty == false ? saved! : [WheelProfile(name: "Default")]
        self.profiles = profiles
        let selected = UserDefaults.standard.string(forKey: "activeWheelProfile")
        currentID = profiles.first { $0.id.uuidString == selected }?.id ?? profiles[0].id
    }
    var choices: [(UUID, String)] { profiles.map { ($0.id, $0.name) } }
    private var index: Int { profiles.firstIndex { $0.id == currentID } ?? 0 }
    var pins: Set<String> { profiles[index].pins }
    func visible(_ key: String) -> Bool { !profiles[index].hidden.contains(key) }
    func setVisible(_ visible: Bool, key: String) {
        if visible { profiles[index].hidden.remove(key) } else { profiles[index].hidden.insert(key) }
        persist()
    }
    func pin(_ id: String, enabled: Bool) {
        if enabled { profiles[index].pins.insert(id) } else { profiles[index].pins.remove(id) }
        persist()
    }
    func select(_ id: UUID) { currentID = id; persist() }
    func add(_ name: String) {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        let item = WheelProfile(name: name)
        profiles.append(item); select(item.id)
    }
    func reset() { profiles[index].hidden = []; profiles[index].pins = []; persist() }
    private func persist() {
        if let data = try? JSONEncoder().encode(profiles) { defaults.set(data, forKey: "wheelProfiles") }
        defaults.set(currentID.uuidString, forKey: "activeWheelProfile")
    }
}

struct PackagePinControl: View {
    @ObservedObject private var preferences = WheelPreferences.shared
    let package: OutputPackage
    var body: some View {
        Toggle("Pin to the conversion wheel", isOn: Binding(
            get: { preferences.pins.contains(package.id) },
            set: { preferences.pin(package.id, enabled: $0) }))
    }
}

extension WheelItem {
    var preferenceKey: String? {
        switch operation {
        case .convert(let format): return "format." + format
        case .tool(let tool): return "tool." + tool.rawValue
        case nil: return action.map { "action." + $0.rawValue }
        }
    }
}

@MainActor enum WheelPause {
    private static var checkedAt: TimeInterval = -.infinity
    private static var cached: String?
    private static var cachedPID: pid_t?
    static func reason(force: Bool = false) -> String? {
        guard let app = NSWorkspace.shared.frontmostApplication, app.bundleIdentifier != Bundle.main.bundleIdentifier else { return nil }
        let now = ProcessInfo.processInfo.systemUptime
        if !force, app.processIdentifier == cachedPID, now - checkedAt < 0.4 { return cached }
        checkedAt = now; cachedPID = app.processIdentifier
        let apps = (UserDefaults.standard.string(forKey: "wheelExcludedApps") ?? "").components(separatedBy: "\n")
        if let id = app.bundleIdentifier, apps.contains(id) {
            cached = L10n.text("Wheel paused") + " · " + (app.localizedName ?? id)
        } else if UserDefaults.standard.bool(forKey: "pauseWheelFullScreen"), isFullScreen(app.processIdentifier) {
            cached = L10n.text("Wheel paused in full screen")
        } else { cached = nil }
        return cached
    }
    private static func isFullScreen(_ pid: pid_t) -> Bool {
        if AXIsProcessTrusted() {
            let app = AXUIElementCreateApplication(pid)
            var window: CFTypeRef?
            if AXUIElementCopyAttributeValue(app, kAXFocusedWindowAttribute as CFString, &window) == .success,
               let window, CFGetTypeID(window) == AXUIElementGetTypeID() {
                var value: CFTypeRef?
                if AXUIElementCopyAttributeValue(unsafeBitCast(window, to: AXUIElement.self), "AXFullScreen" as CFString, &value) == .success {
                    return (value as? NSNumber)?.boolValue ?? false
                }
            }
        }
        let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
        return windows?.contains { entry in
            guard entry[kCGWindowOwnerPID as String] as? Int32 == pid,
                  entry[kCGWindowLayer as String] as? Int == 0,
                  let bounds = entry[kCGWindowBounds as String] as? [String: Any],
                  let frame = CGRect(dictionaryRepresentation: bounds as CFDictionary) else { return false }
            return NSScreen.screens.contains { screen in
                guard let id = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber else { return false }
                return frame.equalTo(CGDisplayBounds(id.uint32Value))
            }
        } ?? false
    }
}

struct WheelSettings: View {
    @ObservedObject private var prefs = WheelPreferences.shared
    @State private var name = ""
    @State private var mode = WheelMode.convert
    @AppStorage("showWheelHint") private var showHint = true
    @AppStorage("pauseWheelFullScreen") private var pauseFullScreen = false
    @AppStorage("wheelExcludedApps") private var excluded = ""
    private var items: [WheelItem] {
        switch mode {
        case .convert: return Set(FeatureCatalog.conversionMatrix.values.flatMap { $0 }).sorted().map { WheelItem(title: $0.uppercased(), operation: .convert($0)) }
        case .tools: return ToolKind.allCases.map { WheelItem(title: FeatureCatalog.toolNames[$0] ?? $0.title, operation: .tool($0)) }
        case .actions: return FileAction.allCases.map { WheelItem(title: $0.title, symbol: $0.symbol, action: $0) }
        }
    }
    private var examples: [WheelItem] {
        let selection = URL(fileURLWithPath: "/Example.png")
        let compatible: [WheelItem]
        switch mode {
        case .convert: compatible = FeatureCatalog.formats(for: [selection]).map { WheelItem(title: $0.uppercased(), operation: .convert($0)) }
        case .tools: compatible = FeatureCatalog.tools(for: [selection]).map { WheelItem(title: FeatureCatalog.toolNames[$0] ?? $0.title, operation: .tool($0)) }
        case .actions: compatible = items
        }
        let visible = compatible.filter { $0.preferenceKey.map(prefs.visible) ?? true }
        return visible.isEmpty ? [WheelItem(title: "All compatible actions", symbol: "list.bullet")]:visible
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Wheel settings").font(.title.bold())
                GroupBox("Profile") {
                    VStack(alignment: .leading, spacing: 12) {
                        Picker("Active profile", selection: Binding(get: { prefs.currentID }, set: prefs.select)) {
                            ForEach(prefs.choices, id: \.0) { item in Text(verbatim: item.1).tag(item.0) }
                        }
                        HStack { TextField("New profile name", text: $name); Button("Add profile") { prefs.add(name); name = "" }.disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) }
                        Picker("Wheel", selection: $mode) { Text("Convert").tag(WheelMode.convert); Text("Tools").tag(WheelMode.tools); Text("File actions").tag(WheelMode.actions) }.pickerStyle(.segmented)
                        HStack(alignment: .center, spacing: 8) {
                            ScrollView {
                                LazyVStack(alignment: .leading, spacing: 8) {
                                    ForEach(items, id: \.preferenceKey) { item in
                                        if let key = item.preferenceKey {
                                            Toggle(isOn: Binding(get: { prefs.visible(key) }, set: { prefs.setVisible($0, key: key) })) { LText(item.title) }.toggleStyle(.checkbox)
                                        }
                                    }
                                }
                            }.frame(minWidth: 170, maxHeight: 220)
                            VStack { WelcomeWheelPreview(mode: mode, items: examples).frame(width: 180, height: 180); Text("Preview for a PNG image").font(.caption) }
                        }
                        Button("Restore wheel defaults") { prefs.reset() }
                        Text("Home lists all compatible actions. Pin saved packages in Output packages.").font(.caption).foregroundStyle(.secondary)
                    }
                }
                GroupBox("Wheel shortcuts") {
                    VStack(alignment: .leading, spacing: 12) {
                        WheelKeyPickers()
                        Toggle("Show shortcut hints beside the wheel", isOn: $showHint)
                    }
                }
                GroupBox("Pause global wheels") {
                    VStack(alignment: .leading, spacing: 12) {
                        Toggle("Pause in full-screen applications", isOn: $pauseFullScreen)
                        ForEach(excluded.components(separatedBy: "\n").filter { !$0.isEmpty }, id: \.self) { id in
                            HStack {
                                let name = NSWorkspace.shared.urlForApplication(withBundleIdentifier: id)?.deletingPathExtension().lastPathComponent ?? id
                                Text(verbatim: name); Spacer()
                                Button { excluded = excluded.components(separatedBy: "\n").filter { $0 != id }.joined(separator: "\n") } label: { Image(systemName: "minus.circle") }.accessibilityLabel("Remove \(name)")
                            }
                        }
                        Button("Choose application…") {
                            let panel = NSOpenPanel()
                            panel.directoryURL = URL(fileURLWithPath: "/Applications")
                            panel.allowedContentTypes = [.applicationBundle]
                            if panel.runModal() == .OK, let url = panel.url, let id = Bundle(url: url)?.bundleIdentifier {
                                excluded = Set((excluded.components(separatedBy: "\n") + [id]).filter { !$0.isEmpty }).sorted().joined(separator: "\n")
                            }
                        }
                    }
                }
            }.padding(24)
        }
    }
}

private struct WheelKeyPickers: View {
    @State private var revision = 0
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(WheelShortcut.allCases) { wheel in
                Picker(L10n.text(wheel.title), selection: Binding(
                    get: { ModifierPreferences.chord(for: wheel).rawValue },
                    set: { if ModifierPreferences.set(.init(rawValue: $0), for: wheel) { revision += 1 } })) {
                    ForEach(ModifierPreferences.available(for: wheel)) { chord in Text(verbatim: chord.symbols + "  " + chord.title).tag(chord.rawValue) }
                }
            }
        }.id(revision)
    }
}
