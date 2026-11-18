import AppKit
import PivokiCore
import SwiftUI

@MainActor final class PackageWorkspace: ObservableObject {
    @Published private(set) var packages: [OutputPackage] = []
    @Published var selectedID = "" { didSet { if oldValue != selectedID { invalidate() } } }
    @Published var inputs: [URL] = [] { didSet { invalidate() } }
    @Published var destination: URL? { didSet { invalidate() } }
    @Published var recursive = false { didSet { invalidate() } }
    @Published var conflictPolicy = "keep-both" { didSet { invalidate() } }
    @Published private(set) var preview: PackageReply?
    @Published private(set) var result: PackageReply?
    @Published private(set) var message = ""
    @Published private(set) var busy = false
    @Published private(set) var running = false
    @Published private(set) var cancelling = false
    @Published var editing = false
    private weak var state: AppState?
    private var request: PackageRPC?
    init(state: AppState) { self.state = state }
    var selected: OutputPackage? { packages.first { $0.id == selectedID } }
    var readyRows: Int { preview?.rows?.filter { $0.status == "planned" }.count ?? 0 }

    private func invalidate() {
        preview = nil
        result = nil
        message = ""
    }

    func load(preferred: String? = nil) async {
        guard !busy else { return }
        do {
            let reply = try await PackageRPC().send(["action": "packages"])
            guard reply.status == "success" else { throw PivokiError.failed(reply.error ?? reply.status) }
            let previous = selected
            packages = reply.packages ?? []
            if let preferred, packages.contains(where: { $0.id == preferred }) { selectedID = preferred }
            else if selected == nil { selectedID = packages.first?.id ?? "" }
            if let previous, previous != selected { invalidate() }
            state?.wheelPackages = packages
        } catch { message = error.localizedDescription }
    }

    func save(_ package: OutputPackage) async -> String? {
        do {
            let definition = try JSONSerialization.jsonObject(with: JSONEncoder().encode(package))
            let reply = try await PackageRPC().send(["action": "savePackage", "package": definition])
            guard reply.status == "success", let saved = reply.package else { return reply.error ?? reply.status }
            invalidate()
            await load(preferred: saved.id)
            editing = false
            return nil
        } catch { return error.localizedDescription }
    }

    func deleteSelected() async {
        guard !busy, let selected else { return }
        do {
            let reply = try await PackageRPC().send(["action": "deletePackage", "packageId": selected.id])
            guard reply.status == "success" else { throw PivokiError.failed(reply.error ?? reply.status) }
            invalidate()
            await load()
        } catch { message = error.localizedDescription }
    }

    func plan() async {
        guard !busy, let selected, let revision = selected.revision, let destination, !inputs.isEmpty else { return }
        busy = true
        invalidate()
        defer { busy = false }
        do {
            let reply = try await PackageRPC().send([
                "action": "plan", "inputs": inputs.map(\.path), "outputRoot": destination.path,
                "recursive": recursive, "packageId": selected.id, "revision": revision, "conflictPolicy": conflictPolicy
            ])
            guard reply.status == "planned" else { throw PivokiError.failed(reply.error ?? reply.status) }
            preview = reply
        } catch { message = error.localizedDescription }
    }

    func cancel() {
        guard running, !cancelling else { return }
        cancelling = true
        request?.cancel()
    }

    func run() async {
        guard !busy, let id = preview?.planId, readyRows > 0, let state, !state.working else { return }
        busy = true
        running = true
        let rpc = PackageRPC()
        request = rpc
        state.beginJob("Creating package outputs")
        let timer = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: true) { [weak self, weak state] _ in
            Task { @MainActor in if state?.token.isCancelled == true { self?.cancel() } }
        }
        defer {
            timer.invalidate()
            busy = false; running = false; cancelling = false
            request = nil; state.finishJob()
        }
        do {
            let reply = try await rpc.send(["action": "run", "planId": id])
            preview = nil
            switch reply.status {
            case "success":
                result = reply
                await state.refreshPackageHistory()
                state.outputs = (reply.paths ?? []).map { URL(fileURLWithPath: $0) }
                state.reportSuccess(.filesReady(state.outputs))
            case "cancelled", "skipped": message = reply.error ?? (reply.status == "cancelled" ? "Cancelled" : "Skipped")
            default: message = reply.error ?? reply.status
            }
        } catch {
            preview = nil
            message = error is CancellationError ? "Cancelled" : error.localizedDescription
        }
    }
}

struct PackageView: View {
    @ObservedObject var model: PackageWorkspace
    @ObservedObject var state: AppState
    @State private var draft = Self.freshPackage()
    @State private var deletePrompt = false
    @State private var showRows = true
    @State private var showSettings = false
    private static func freshPackage() -> OutputPackage {
        OutputPackage(name: "", outputs: [.init(format: "webp", maxEdge: 1600, relativeDir: "web"), .init(format: "jpg", maxEdge: 400, relativeDir: "thumb")])
    }
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "square.3.layers.3d").font(.title).foregroundStyle(PivokiPalette.forest)
                Text("Output packages").font(.title.bold())
                Spacer()
                Button("New package") { draft = Self.freshPackage(); model.editing = true }
                    .buttonStyle(PivokiButtonStyle(.secondary, compact: true)).disabled(model.busy)
            }.padding(24)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if model.preview != nil || model.result != nil {
                        DisclosureGroup(isExpanded: $showSettings) { configuration.disabled(model.busy) } label: {
                            Text(verbatim: model.selected?.name ?? L10n.text("Package")).font(.headline)
                        }
                    } else { configuration.disabled(model.busy) }
                    if let preview = model.preview { previewCard(preview) }
                    if let result = model.result { resultCard(result) }
                    if !model.message.isEmpty { Label { LText(model.message).textSelection(.enabled) } icon: { Image(systemName: "info.circle") } }
                }.padding(24)
            }
            Divider()
            HStack(spacing: 12) {
                if model.busy {
                    ProgressView().controlSize(.small)
                    LText(model.running ? (model.cancelling ? "Cancelling…" : "Creating package outputs") : "Preparing output plan")
                }
                Spacer()
                if model.running {
                    Button("Cancel") { model.cancel() }.disabled(model.cancelling)
                } else if model.preview != nil {
                    Button("Create outputs") { Task { await model.run() } }
                        .buttonStyle(PivokiButtonStyle(.primary)).disabled(model.readyRows == 0 || state.working)
                } else {
                    Button("Preview output plan") { Task { await model.plan() } }
                        .buttonStyle(PivokiButtonStyle(.primary))
                        .disabled(model.busy || model.selected == nil || model.destination == nil || model.inputs.isEmpty || state.working)
                }
            }.padding(16)
        }
        .frame(minWidth: 680, minHeight: 510)
        .background(PivokiPalette.canvas)
        .onChange(of: model.preview?.planId) { _ in showSettings = false }
        .sheet(isPresented: $model.editing) { PackageEditor(model: model, draft: draft) }
        .alert("Delete this package?", isPresented: $deletePrompt) {
            Button("Cancel", role: .cancel) {}
            Button("Delete", role: .destructive) { Task { await model.deleteSelected() } }
        } message: { Text(verbatim: model.selected?.name ?? "") }
    }

    private var configuration: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                if !model.packages.isEmpty {
                    Picker("Package", selection: $model.selectedID) {
                        ForEach(model.packages) { package in Text(verbatim: "\(package.name) · r\(package.revision ?? 1)").tag(package.id) }
                    }
                } else { Text("Create a package to define your output formats and sizes.") }
                Spacer()
                if let selected = model.selected {
                    Button("Edit") { draft = selected; model.editing = true }
                    Button { deletePrompt = true } label: { Image(systemName: "trash") }.accessibilityLabel("Delete package")
                }
            }
            if let package = model.selected {
                ForEach(Array(package.outputs.enumerated()), id: \.offset) { _, row in
                    HStack { Text(row.format.uppercased()).font(.caption.bold()).frame(width: 50, alignment: .leading); Text("\(row.maxEdge) px"); Spacer(); Image(systemName: "folder"); Text(verbatim: row.relativeDir.isEmpty ? "." : row.relativeDir) }.font(.callout)
                }
                PackagePinControl(package: package)
            }
            Divider()
            HStack { Text("Sources").bold(); Spacer(); Button("Choose files or folders…") { chooseInput() } }
            if !model.inputs.isEmpty {
                ForEach(model.inputs, id: \.self) { url in Text(verbatim: url.path).textSelection(.enabled) }.font(.caption)
            }
            Toggle("Include subfolders", isOn: $model.recursive)
            Divider()
            HStack { Text("Output folder").bold(); Spacer(); Button("Choose folder…") { chooseDestination() } }
            if let destination = model.destination { Text(verbatim: destination.path).font(.callout).textSelection(.enabled) }
            Picker("Name conflicts", selection: $model.conflictPolicy) {
                Text("Keep both").tag("keep-both"); Text("Skip existing names").tag("skip")
            }.pickerStyle(.segmented)
        }.padding(20).pivokiCard(radius: 16)
    }

    private func previewCard(_ preview: PackageReply) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Output plan").font(.headline)
            HStack { Text("\(preview.inputCount ?? 0) sources"); Text("·"); Text("\(model.readyRows) outputs"); Text("·"); Text("\(preview.conflictCount ?? 0) name conflicts"); Text("·"); Text("\((preview.skipped?.count ?? 0) + (preview.rows?.filter { $0.status == "skipped" }.count ?? 0)) skipped") }
                .foregroundStyle(.secondary)
            DisclosureGroup("Planned paths", isExpanded: $showRows) {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(Array((preview.rows ?? []).enumerated()), id: \.offset) { _, row in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(verbatim: row.source).font(.caption).foregroundStyle(.secondary)
                            if let original = row.originalTarget, original != row.target {
                                Text(verbatim: original).strikethrough().font(.caption).foregroundStyle(.secondary)
                            }
                            if let target = row.target { Label { Text(verbatim: target) } icon: { Image(systemName: "arrow.turn.down.right") } }
                            if let reason = row.reason, !reason.isEmpty { Text(verbatim: reason).font(.caption) }
                        }.textSelection(.enabled)
                        Divider()
                    }
                    ForEach(Array((preview.skipped ?? []).enumerated()), id: \.offset) { _, item in
                        Text(verbatim: "\(item.source) · \(item.reason)").font(.callout).textSelection(.enabled)
                    }
                }.padding(.top, 8)
            }
        }.padding(20).pivokiCard(radius: 16)
    }

    private func resultCard(_ result: PackageReply) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Outputs saved", systemImage: "checkmark.circle.fill").font(.headline)
            ForEach(result.paths ?? [], id: \.self) { path in Text(verbatim: path).font(.caption).textSelection(.enabled) }
            if let directory = result.directory {
                Button("Show output folder") { NSWorkspace.shared.open(URL(fileURLWithPath: directory, isDirectory: true)) }
            }
        }.padding(20).pivokiCard(radius: 16)
    }
    private func chooseInput() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true; panel.allowsMultipleSelection = true
        if panel.runModal() == .OK { model.inputs = panel.urls }
    }
    private func chooseDestination() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false; panel.canChooseDirectories = true; panel.canCreateDirectories = true
        if panel.runModal() == .OK { model.destination = panel.url }
    }
}

private struct PackageEditor: View {
    @ObservedObject var model: PackageWorkspace
    @State var draft: OutputPackage
    @State private var error = ""
    @State private var saving = false
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            LText(draft.packageId == nil ? "New package" : "Edit package").font(.title2.bold())
            TextField("Package name", text: $draft.name)
            HStack { Text("Format").frame(width: 95, alignment: .leading); Text("Longest edge (px)").frame(width: 130); Text("Relative folder"); Spacer() }.font(.caption).foregroundStyle(.secondary)
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(draft.outputs.indices, id: \.self) { i in
                        HStack {
                            Picker("Output format", selection: $draft.outputs[i].format) {
                                ForEach(["webp", "jpg", "png"], id: \.self) { Text($0.uppercased()).tag($0) }
                            }.labelsHidden().frame(width: 95)
                            TextField("Longest edge", value: $draft.outputs[i].maxEdge, format: .number.grouping(.never)).frame(width: 130)
                            TextField("Relative folder", text: $draft.outputs[i].relativeDir)
                            Button { draft.outputs.remove(at: i) } label: { Image(systemName: "minus.circle") }
                                .accessibilityLabel("Remove output").disabled(draft.outputs.count == 1)
                        }
                    }
                }
            }.frame(minHeight: 90, maxHeight: 240)
            Button("Add output") { draft.outputs.append(.init(format: "png", maxEdge: 800, relativeDir: "")) }
            if !error.isEmpty { Text(verbatim: error).foregroundStyle(.red).textSelection(.enabled) }
            HStack {
                Spacer()
                Button("Cancel") { model.editing = false }.keyboardShortcut(.cancelAction)
                Button("Save package") {
                    saving = true
                    Task { if let failure = await model.save(draft) { error = failure }; saving = false }
                }.keyboardShortcut(.defaultAction)
                    .disabled(draft.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || draft.outputs.contains { $0.maxEdge < 1 })
            }
        }.disabled(saving).padding(24).frame(width: 620).background(PivokiPalette.canvas)
    }
}
