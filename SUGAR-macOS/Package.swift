// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "SUGARMac",
    platforms: [.macOS(.v13)],
    targets: [.executableTarget(name: "SUGARMac", path: "Sources")]
)
