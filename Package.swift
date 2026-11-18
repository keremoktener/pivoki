// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Pivoki",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "PivokiCore", targets: ["PivokiCore"]),
        .executable(name: "Pivoki", targets: ["PivokiApp"]),
        .executable(name: "pivoki-cli", targets: ["PivokiCLI"])
    ],
    targets: [
        .target(name: "PivokiCore", resources: [.copy("Resources")]),
        .executableTarget(name: "PivokiApp", dependencies: ["PivokiCore"]),
        .executableTarget(name: "PivokiCLI", dependencies: ["PivokiCore"]),
        .testTarget(name: "PivokiAppTests", dependencies: ["PivokiApp"]),
        .testTarget(name: "PivokiCoreTests", dependencies: ["PivokiCore"], resources: [.copy("Fixtures")])
    ],
    swiftLanguageModes: [.v5]
)
