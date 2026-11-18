import AppKit
import ServiceManagement
import SwiftUI

protocol LoginItemService {
    var status: SMAppService.Status { get }
    func register() throws
    func unregister() throws
}

extension SMAppService: LoginItemService {}

final class LoginItemController: ObservableObject {
    static let shared = LoginItemController(service: SMAppService.mainApp, defaults: .standard,
                                            canRegister: canRegister(from: Bundle.main.bundleURL))
    private let service: LoginItemService
    private let defaults: UserDefaults
    private let configuredKey = "loginItemDefaultApplied"
    let canRegister: Bool
    @Published private(set) var status: SMAppService.Status
    @Published private(set) var errorMessage: String?

    init(service: LoginItemService, defaults: UserDefaults, canRegister: Bool = true) {
        self.service = service
        self.defaults = defaults
        self.canRegister = canRegister
        status = service.status
    }

    static func canRegister(from url: URL) -> Bool {
        guard url.pathExtension == "app", !url.pathComponents.contains("AppTranslocation") else { return false }
        return (try? url.resourceValues(forKeys: [.volumeIsReadOnlyKey]).volumeIsReadOnly) != true
    }

    func refresh() {
        let current = service.status
        if current != status {
            status = current
            errorMessage = nil
        }
    }

    func applyDefault() {
        refresh()
        guard !defaults.bool(forKey: configuredKey) else { return }
        if defaults.object(forKey: configuredKey) == nil {
            // Keep a legacy user's unregistered record. A false marker means a new
            // installation still needs its first successful registration (e.g. after moving off a DMG).
            let legacyOptOut = defaults.bool(forKey: "hasOpened") && status == .notRegistered
            defaults.set(legacyOptOut, forKey: configuredKey)
            if legacyOptOut { return }
        }
        setEnabled(true)
    }

    var isRegistered: Bool { status == .enabled || status == .requiresApproval }

    func setEnabled(_ enabled: Bool) {
        guard canRegister else { return }
        refresh()
        errorMessage = nil
        do {
            if enabled && !isRegistered {
                try service.register()
            } else if !enabled && isRegistered {
                try service.unregister()
            }
            refresh()
            defaults.set(true, forKey: configuredKey)
        } catch {
            refresh()
            if enabled && isRegistered {
                defaults.set(true, forKey: configuredKey)
            } else {
                errorMessage = error.localizedDescription
            }
        }
    }
}

struct LoginItemToggle: View {
    let title: LocalizedStringKey
    @ObservedObject private var controller = LoginItemController.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Toggle(title, isOn: Binding(get: { controller.isRegistered }, set: controller.setEnabled))
                .disabled(!controller.canRegister)
            if !controller.canRegister {
                Text("Move Pivoki to Applications and open it there to enable launch at login.")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                if controller.status == .requiresApproval {
                    Text("Allow Pivoki in macOS Login Items.").font(.caption).foregroundStyle(.secondary)
                }
                if let message = controller.errorMessage {
                    Text(verbatim: message).font(.caption).foregroundStyle(.secondary)
                }
                if controller.status == .requiresApproval || controller.errorMessage != nil {
                    Button("Open Login Items") { SMAppService.openSystemSettingsLoginItems() }
                }
            }
        }
        .onAppear(perform: controller.refresh)
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in controller.refresh() }
    }
}
