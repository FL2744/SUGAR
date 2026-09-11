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
    private var rawBackendLog = ""

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
        if let issue = preflight(command: command, config: config) {
            log = issue
            return
        }
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
        let needsLLM = (config["translate_posts"] as? Bool ?? true)
            || (config["infer_locations"] as? Bool ?? true)
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
        rawBackendLog = ""
        log = "Starting \(command)…\n\(Self.appDiagnostics())\n"
        Task {
            do {
                let result = try await Task.detached {
                    try await Self.execute(command: command, configData: configData, secrets: secrets) { line in
                        self.rawBackendLog += line
                        self.log += Self.renderBackendLog(line) + "\n"
                        self.outputs = Self.outputPaths(from: self.rawBackendLog)
                    }
                }.value
                outputs = Self.outputPaths(from: rawBackendLog)
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
        do {
            return try await BackendRunner.run(process, onOutput: onOutput)
        } catch {
            throw NSError(domain: "SUGAR", code: 2, userInfo: [NSLocalizedDescriptionKey:
                "Bundled backend could not start. App architecture: \(compiledArchitecture()); backend architecture: \(binaryArchitectures(backend)). \(error.localizedDescription)"])
        }
    }

    private func preflight(command: String, config: [String: Any]) -> String? {
        if command == "search" {
            let sources = (config["sources"] as? [String]) ?? []
            if sources.contains("x") && xToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return "Cannot start search: X is selected, but no X bearer token is saved. Open Settings, enter the token, and try again."
            }
            if let output = config["output_directory"] as? String, !output.isEmpty {
                let path = (output as NSString).expandingTildeInPath
                do {
                    try FileManager.default.createDirectory(
                        atPath: path, withIntermediateDirectories: true, attributes: nil
                    )
                } catch {
                    return "Cannot use the selected output folder: \(error.localizedDescription)"
                }
                if !FileManager.default.isWritableFile(atPath: path) {
                    return "Cannot use the selected output folder because it is not writable: \(path)"
                }
            }
        } else if let source = config["source_file"] as? String,
                  !FileManager.default.isReadableFile(atPath: source) {
            return "Cannot read the selected source file: \(source)"
        }
        return nil
    }

    func copyLog() {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(log, forType: .string)
    }

    nonisolated static func appDiagnostics() -> String {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
        let os = ProcessInfo.processInfo.operatingSystemVersionString
        return "SUGAR \(version) • \(os) • app \(compiledArchitecture())"
    }

    nonisolated static func compiledArchitecture() -> String {
        #if arch(arm64)
        return "arm64"
        #elseif arch(x86_64)
        return "x86_64"
        #else
        return "unknown"
        #endif
    }

    nonisolated static func binaryArchitectures(_ url: URL) -> String {
        let process = Process()
        let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/lipo")
        process.arguments = ["-archs", url.path]
        process.standardOutput = pipe
        process.standardError = Pipe()
        do {
            try process.run()
            process.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let text = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return text.isEmpty ? "unknown" : text
        } catch {
            return "unknown"
        }
    }

    nonisolated static func renderBackendLog(_ raw: String) -> String {
        var lines: [String] = []
        for rawLine in raw.split(separator: "\n") {
            let line = String(rawLine)
            guard let data = line.data(using: .utf8),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let event = json["event"] as? String else {
                lines.append(line)
                continue
            }
            switch event {
            case "backend", "diagnostics":
                let version = json["version"] as? String ?? "unknown"
                let architecture = json["architecture"] as? String ?? "unknown"
                let python = json["python"] as? String ?? "unknown"
                let runtime = json["runtime"] as? String ?? "unknown"
                lines.append("Backend \(version) • \(architecture) • Python \(python) • \(runtime)")
            case "starting":
                if let operation = json["operation"] as? String {
                    lines.append("Preparing \(operation)…")
                }
            case "translating_search_terms":
                lines.append("Translating search terms…")
            case "search_term_progress":
                lines.append(progressLine("Search-term translation", json: json))
            case "authenticating":
                lines.append("Authenticating \((json["source"] as? String ?? "source").capitalized)…")
            case "collecting":
                lines.append("Collecting \((json["source"] as? String ?? "source").capitalized)…")
            case "collected":
                let source = (json["source"] as? String ?? "source").capitalized
                let count = json["records"] as? Int ?? 0
                lines.append("\(source): \(count) records collected")
            case "enriching":
                let count = json["records"] as? Int ?? 0
                lines.append("Enriching \(count) records…")
            case "detecting_languages":
                lines.append("Detecting languages…")
            case "language_progress":
                lines.append(progressLine("Language detection", json: json))
            case "translating":
                lines.append("Translating posts…")
            case "translation_progress":
                lines.append(progressLine("Translation", json: json))
            case "inferring_locations":
                lines.append("Inferring broad locations…")
            case "location_progress":
                lines.append(progressLine("Location inference", json: json))
            case "geocoding":
                lines.append("Geocoding supported locations…")
            case "geocode_progress":
                lines.append(progressLine("Geocoding", json: json))
            case "saving":
                lines.append("Saving results…")
            case "saved":
                lines.append("Results saved.")
            case "mapping":
                lines.append("Creating map…")
            case "analyzing":
                lines.append("Creating analysis report…")
            case "complete":
                lines.append("Finished successfully.")
            case "error":
                lines.append("Error: \(json["message"] as? String ?? "Unknown backend error")")
            default:
                continue
            }
        }
        return lines.joined(separator: "\n")
    }

    nonisolated static func progressLine(_ label: String, json: [String: Any]) -> String {
        let current = json["current"] as? Int ?? 0
        let total = json["total"] as? Int ?? 0
        return total > 0 ? "\(label): \(current)/\(total)" : label
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
