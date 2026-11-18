import Darwin
import Foundation

/// The same executable serves the native interface and headless CLI.
public enum PackageEngine {
    public static func executable() throws -> URL {
        let environment = ProcessInfo.processInfo.environment
        let override = environment["PIVOKI_ENGINE"].map { URL(fileURLWithPath: $0) }
        let contents = Bundle.main.bundleURL.appendingPathComponent("Contents")
        let parent = URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL.deletingLastPathComponent()
        let candidates = [
            override,
            contents.appendingPathComponent("Helpers/pivoki-engine/pivoki-engine"),
            contents.appendingPathComponent("MacOS/pivoki-engine"),
            parent.appendingPathComponent("../Helpers/pivoki-engine/pivoki-engine")
        ]
        guard let url = candidates.compactMap({ $0 }).first(where: {
            (try? $0.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true &&
                FileManager.default.isExecutableFile(atPath: $0.path)
        }) else {
            throw PivokiError.missingDependency("pivoki-engine. Use the Pivoki application bundle or set PIVOKI_ENGINE.")
        }
        return url
    }

    /// Replace this process so signals, stdin, stdout and exit status are preserved.
    public static func dispatchCLI(_ arguments: [String]) -> Int32? {
        guard let command = arguments.dropFirst().first,
              !["convert", "tool", "inspect", "catalog", "dependencies"].contains(command) else { return nil }
        do {
            let url = try executable()
            let values = ([url.path] + arguments.dropFirst()).map { strdup($0) } + [nil]
            defer { values.forEach { free($0) } }
            _ = values.withUnsafeBufferPointer { execv(url.path, $0.baseAddress!) }
            throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
        } catch {
            fputs(error.localizedDescription + "\n", stderr)
            return 1
        }
    }
}
