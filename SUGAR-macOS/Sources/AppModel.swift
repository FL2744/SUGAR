import AppKit
import Foundation
import Security

@MainActor
final class AppModel: ObservableObject {
    @Published var isRunning = false
    @Published var log = "Ready."
    @Published var outputs: [String] = []
    @Published var xToken = KeychainStore.read("xBearerToken")
    @Published var llmKey = KeychainStore.read("llmAPIKey")
    @Published var blueskyIdentifier = KeychainStore.read("blueskyIdentifier")
    @Published var blueskyPassword = KeychainStore.read("blueskyPassword")
    @Published var mastodonToken = KeychainStore.read("mastodonToken")

    func saveCredentials() {
        KeychainStore.write(xToken, key: "xBearerToken")
        KeychainStore.write(llmKey, key: "llmAPIKey")
        KeychainStore.write(blueskyIdentifier, key: "blueskyIdentifier")
        KeychainStore.write(blueskyPassword, key: "blueskyPassword")
        KeychainStore.write(mastodonToken, key: "mastodonToken")
        log = "Credentials saved securely in macOS Keychain."
    }

    func run(command: String, config: [String: Any]) {
        guard !isRunning else { return }
        saveCredentials()
        let configData: Data
        do {
            configData = try JSONSerialization.data(withJSONObject: config, options: [.prettyPrinted])
        } catch {
            log = error.localizedDescription
            return
        }
        let secrets = BackendSecrets(
            xToken: xToken, llmKey: llmKey, blueskyIdentifier: blueskyIdentifier,
            blueskyPassword: blueskyPassword, mastodonToken: mastodonToken
        )
        isRunning = true
        outputs = []
        log = "Starting \(command)…\n"
        Task {
            do {
                let result = try await Task.detached {
                    try Self.execute(command: command, configData: configData, secrets: secrets)
                }.value
                log += result.text
                outputs = Self.outputPaths(from: log)
                if result.status != 0 { log += "\nOperation failed." }
            } catch {
                log += "\n\(error.localizedDescription)"
            }
            isRunning = false
        }
    }

    nonisolated static func execute(
        command: String, configData: Data, secrets: BackendSecrets
    ) throws -> BackendResult {
        let configURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("sugar-\(UUID().uuidString).json")
        let logURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("sugar-\(UUID().uuidString).log")
        try configData.write(to: configURL, options: .atomic)
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        defer {
            try? FileManager.default.removeItem(at: configURL)
            try? FileManager.default.removeItem(at: logURL)
        }
        guard let backend = Bundle.main.resourceURL?.appendingPathComponent("sugar-bridge"),
              FileManager.default.isExecutableFile(atPath: backend.path) else {
            throw NSError(domain: "SUGAR", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "Bundled SUGAR backend not found."])
        }
        let process = Process()
        let handle = try FileHandle(forWritingTo: logURL)
        defer { try? handle.close() }
        process.executableURL = backend
        process.arguments = [command, "--config", configURL.path]
        process.standardOutput = handle
        process.standardError = handle
        var environment = ProcessInfo.processInfo.environment
        environment["SUGAR_X_BEARER_TOKEN"] = secrets.xToken
        environment["SUGAR_LLM_API_KEY"] = secrets.llmKey
        environment["SUGAR_BLUESKY_IDENTIFIER"] = secrets.blueskyIdentifier
        environment["SUGAR_BLUESKY_APP_PASSWORD"] = secrets.blueskyPassword
        environment["SUGAR_MASTODON_TOKEN"] = secrets.mastodonToken
        process.environment = environment
        try process.run()
        process.waitUntilExit()
        try handle.synchronize()
        let text = String(data: try Data(contentsOf: logURL), encoding: .utf8) ?? ""
        return BackendResult(status: process.terminationStatus, text: text)
    }

    nonisolated static func outputPaths(from log: String) -> [String] {
        var paths: [String] = []
        for line in log.split(separator: "\n") {
            guard let data = line.data(using: .utf8),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  json["event"] as? String == "complete" else { continue }
            paths.append(contentsOf: json["outputs"] as? [String] ?? [])
        }
        return paths
    }

    func reveal(_ path: String) {
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
    }
}

struct BackendSecrets: Sendable {
    let xToken: String
    let llmKey: String
    let blueskyIdentifier: String
    let blueskyPassword: String
    let mastodonToken: String
}

struct BackendResult: Sendable {
    let status: Int32
    let text: String
}

enum KeychainStore {
    static let service = "edu.vt.sugar.app"
    static func read(_ key: String) -> String {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return "" }
        return String(data: data, encoding: .utf8) ?? ""
    }
    static func write(_ value: String, key: String) {
        let base: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(base as CFDictionary)
        guard !value.isEmpty else { return }
        var add = base
        add[kSecValueData as String] = Data(value.utf8)
        SecItemAdd(add as CFDictionary, nil)
    }
}
