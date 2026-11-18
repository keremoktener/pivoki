import Foundation
import PivokiCore

struct PackageOutput: Codable, Equatable {
    var format: String
    var maxEdge: Int
    var relativeDir: String
}

struct OutputPackage: Codable, Identifiable, Equatable {
    var packageId: String?
    var revision: Int?
    var name: String
    var outputs: [PackageOutput]
    var id: String { packageId ?? "" }
}

struct OutputRow: Decodable {
    let source: String
    let target: String?
    let originalTarget: String?
    let status: String
    let reason: String?
}

struct PackageReply: Decodable {
    struct Skipped: Decodable { let source: String; let reason: String }
    struct Job: Decodable { let jobId: String; let name: String; let directory: String; let paths: [String]; let createdAt: String }
    let status: String
    let error: String?
    let code: String?
    let packages: [OutputPackage]?
    let package: OutputPackage?
    let rows: [OutputRow]?
    let skipped: [Skipped]?
    let inputCount: Int?
    let conflictCount: Int?
    let planId: String?
    let jobId: String?
    let paths: [String]?
    let directory: String?
    let jobs: [Job]?
}

enum StudioLauncher {
    @MainActor static func open(inputs: [URL], onExit: @escaping @MainActor (Int32) -> Void) throws {
        let process = Process()
        process.executableURL = try PackageEngine.executable()
        process.arguments = ["studio"] + inputs.filter(\.isFileURL).map(\.path)
        process.terminationHandler = { process in
            guard process.terminationStatus != 0 else { return }
            Task { @MainActor in onExit(process.terminationStatus) }
        }
        try process.run()
    }
}

final class PackageRPC: @unchecked Sendable {
    private let lock = NSLock()
    private var child: Process?
    private var interrupted = false

    func cancel() {
        lock.lock()
        defer { lock.unlock() }
        interrupted = true
        if let child, child.isRunning { child.interrupt() }
    }

    func send(_ request: [String: Any]) async throws -> PackageReply {
        let input = try JSONSerialization.data(withJSONObject: request)
        return try await Task.detached(priority: .userInitiated) { try self.invoke(input) }.value
    }

    private func launch(_ process: Process) throws {
        lock.lock()
        defer { lock.unlock() }
        guard !interrupted else { throw CancellationError() }
        try process.run()
        child = process
    }

    private func invoke(_ input: Data) throws -> PackageReply {
        let process = Process(), stdin = Pipe(), stdout = Pipe()
        process.executableURL = try PackageEngine.executable()
        process.arguments = ["rpc"]
        process.standardInput = stdin
        process.standardOutput = stdout
        try launch(process)
        defer { lock.lock(); child = nil; lock.unlock() }
        try stdin.fileHandleForWriting.write(contentsOf: input)
        try stdin.fileHandleForWriting.close()
        let data = try stdout.fileHandleForReading.readToEnd() ?? Data()
        process.waitUntilExit()
        lock.lock(); let cancelled = interrupted; lock.unlock()
        if data.isEmpty && cancelled { throw CancellationError() }
        guard let reply = try? JSONDecoder().decode(PackageReply.self, from: data) else {
            throw PivokiError.failed("The package engine returned an unreadable result.")
        }
        return reply
    }
}
