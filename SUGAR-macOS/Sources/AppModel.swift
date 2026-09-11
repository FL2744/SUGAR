import AppKit
import Foundation
import Security

@MainActor
final class AppModel: ObservableObject {
    @Published var isRunning = false
    @Published var log = "Ready."
    @Published var outputs: [String] = []
    @Published var xToken = KeychainStore.read("xBearerToken")
    @Published var openAIKey = KeychainStore.read(LLMProvider.openAI.keychainAccount)
    @Published var arcKey = KeychainStore.read(LLMProvider.arc.keychainAccount)
    @Published var customLLMKey = KeychainStore.read(LLMProvider.custom.keychainAccount)
    @Published private(set) var legacyLLMKey = KeychainStore.read("llmAPIKey")
    private var previousKeyAssigned = false

    func assignPreviousKey(to provider: LLMProvider) {
        switch provider {
        case .openAI: openAIKey = legacyLLMKey
        case .arc: arcKey = legacyLLMKey
        case .custom: customLLMKey = legacyLLMKey
        }
        // Keep the original Keychain entry until the new credentials are saved.
        legacyLLMKey = ""
        previousKeyAssigned = true
    }
    @Published var blueskyIdentifier = KeychainStore.read("blueskyIdentifier")
    @Published var blueskyPassword = KeychainStore.read("blueskyPassword")
    @Published var mastodonToken = KeychainStore.read("mastodonToken")

    @discardableResult
    func saveCredentials() -> Bool {
        let entries = [
            ("xBearerToken", xToken),
            (LLMProvider.openAI.keychainAccount, openAIKey),
            (LLMProvider.arc.keychainAccount, arcKey),
            (LLMProvider.custom.keychainAccount, customLLMKey),
            ("blueskyIdentifier", blueskyIdentifier),
            ("blueskyPassword", blueskyPassword),
            ("mastodonToken", mastodonToken),
        ]
        for (account, value) in entries {
            let status = KeychainStore.write(value, key: account)
            guard status == errSecSuccess else {
                log += "\nCould not save credentials to Keychain (error \(status)).\n"
                return false
            }
        }
        if previousKeyAssigned {
            let status = KeychainStore.write("", key: "llmAPIKey")
            guard status == errSecSuccess else {
                log += "\nProvider keys saved, but the previous shared key could not be removed (error \(status)).\n"
                return false
            }
            previousKeyAssigned = false
        }
        log += "\nCredentials saved securely in macOS Keychain.\n"
        return true
    }

    func run(command: String, config: [String: Any]) {
        guard !isRunning else { return }
        guard saveCredentials() else { return }
        let configData: Data
        do {
            configData = try JSONSerialization.data(withJSONObject: config, options: [.prettyPrinted])
        } catch {
            log = error.localizedDescription
            return
        }
        let llm = config["llm"] as? [String: String] ?? [:]
        let provider = LLMProvider(rawValue: llm["provider"] ?? "openai")
        guard command != "search" || provider != nil else {
            log = "Choose a valid LLM provider."
            return
        }
        let selectedKey = provider?.apiKey(openAI: openAIKey, arc: arcKey, custom: customLLMKey) ?? ""
        let needsLLM = config["translate_posts"] as? Bool == true
            || config["infer_locations"] as? Bool == true
            || !(config["translate_term_languages"] as? [String] ?? []).isEmpty
        if command == "search", needsLLM, selectedKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            log = "Enter the \(provider!.title) API key in Settings before running this search."
            return
        }
        let secrets = BackendSecrets(
            xToken: xToken, llmKey: command == "search" ? selectedKey : "", blueskyIdentifier: blueskyIdentifier,
            blueskyPassword: blueskyPassword, mastodonToken: mastodonToken
        )
        isRunning = true
        outputs = []
        log = "Starting \(command)…\n"
        Task {
            do {
                let result = try await Task.detached {
                    try await Self.execute(command: command, configData: configData, secrets: secrets) { line in
                        self.log += line
                    }
                }.value
                outputs = Self.outputPaths(from: log)
                log += result == 0 ? "\nOperation completed.\n" : "\nOperation failed (exit code \(result)).\n"
            } catch {
                log += "\n\(error.localizedDescription)"
            }
            isRunning = false
        }
    }

    nonisolated static func execute(
        command: String, configData: Data, secrets: BackendSecrets,
        onOutput: @escaping @MainActor @Sendable (String) -> Void
    ) async throws -> Int32 {
        let configURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("sugar-\(UUID().uuidString).json")
        try configData.write(to: configURL, options: .atomic)
        defer {
            try? FileManager.default.removeItem(at: configURL)
        }
        guard let backend = Bundle.main.resourceURL?.appendingPathComponent("sugar-bridge"),
              FileManager.default.isExecutableFile(atPath: backend.path) else {
            throw NSError(domain: "SUGAR", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "Bundled SUGAR backend not found."])
        }
        let process = Process()
        process.executableURL = backend
        process.arguments = [command, "--config", configURL.path]
        var environment = ProcessInfo.processInfo.environment
        environment["SUGAR_X_BEARER_TOKEN"] = secrets.xToken
        environment["SUGAR_LLM_API_KEY"] = secrets.llmKey
        environment["SUGAR_BLUESKY_IDENTIFIER"] = secrets.blueskyIdentifier
        environment["SUGAR_BLUESKY_APP_PASSWORD"] = secrets.blueskyPassword
        environment["SUGAR_MASTODON_TOKEN"] = secrets.mastodonToken
        process.environment = environment
        return try await BackendRunner.run(process, onOutput: onOutput)
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
    static func write(_ value: String, key: String) -> OSStatus {
        let base: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        if value.isEmpty {
            let status = SecItemDelete(base as CFDictionary)
            return status == errSecItemNotFound ? errSecSuccess : status
        }
        let attributes = [kSecValueData as String: Data(value.utf8)]
        let status = SecItemUpdate(base as CFDictionary, attributes as CFDictionary)
        guard status == errSecItemNotFound else { return status }
        var add = base
        add[kSecValueData as String] = Data(value.utf8)
        return SecItemAdd(add as CFDictionary, nil)
    }
}
