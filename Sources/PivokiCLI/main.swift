import Foundation
import PivokiCore

let status = PackageEngine.dispatchCLI(CommandLine.arguments) ?? PivokiCommandLine.run()
// An interrupted job has already cleaned up; end by the same signal so a calling shell stops too.
if [SIGHUP,SIGINT,SIGTERM].contains(status-128) { signal(status-128,SIG_DFL);raise(status-128) }
exit(status)
