import Foundation
import PivokiCore

if CommandLine.arguments.count == 1 || CommandLine.arguments.count == 2 && ["-h", "--help"].contains(CommandLine.arguments[1]) {
    print("""
    Pivoki for macOS
      pivoki-cli convert FORMAT FILE... [--options JSON] [--json]
      pivoki-cli tool TOOL_ID FILE... [--options JSON] [--json]
      pivoki-cli inspect FILE
      pivoki-cli catalog
      pivoki-cli dependencies
      pivoki-cli package list --json
      pivoki-cli package run --help
      pivoki-cli studio [FILE...]
    """)
    exit(0)
}
let status = PackageEngine.dispatchCLI(CommandLine.arguments) ?? PivokiCommandLine.run()
// An interrupted job has already cleaned up; end by the same signal so a calling shell stops too.
if [SIGHUP,SIGINT,SIGTERM].contains(status-128) { signal(status-128,SIG_DFL);raise(status-128) }
exit(status)
