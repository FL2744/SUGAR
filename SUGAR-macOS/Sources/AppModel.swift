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

    private var rawBackendLog = ""

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
        if let issue = preflight(command: command, config: config) {
            log = issue
            return
        }
        saveCredentials()

        let configData: Data
        do {
            configData = try JSONSerialization.data(withJSONObject: config, options: [.prettyPrinted])
        } catch {
            log = "Could not prepare the request: \(error.localizedDescription)"
            return
        }

        let configURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("sugar-\(UUID().uuidString).json")
        let logURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("sugar-\(UUID().uuidString).log")
        do {
            try configData.write(to: configURL, options: .atomic)
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
        } catch {
            log = "Could not create temporary SUGAR files: \(error.localizedDescription)"
            return
        }

        let secrets = BackendSecrets(
            xToken: xToken, llmKey: llmKey, blueskyIdentifier: blueskyIdentifier,
            blueskyPassword: blueskyPassword, mastodonToken: mastodonToken
        )
        isRunning = true
        outputs = []
        rawBackendLog = ""
        log = "Starting \(command)…\n\(Self.appDiagnostics())"

        let poller = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 250_000_000)
                guard let self else { return }
                self.refreshLog(from: logURL, command: command)
            }
        }

        Task {
            defer {
                poller.cancel()
                try? FileManager.default.removeItem(at: configURL)
                try? FileManager.default.removeItem(at: logURL)
                isRunning = false
            }
            do {
                let result = try await Task.detached {
                    try Self.execute(
                        command: command, configURL: configURL, logURL: logURL, secrets: secrets
                    )
                }.value
                refreshLog(from: logURL, command: command)
                if result.status != 0 {
                    log += "\nOperation failed (exit \(result.status))."
                }
            } catch {
                refreshLog(from: logURL, command: command)
                log += "\n\(error.localizedDescription)"
            }
        }
    }

    private func preflight(command: String, config: [String: Any]) -> String? {
        if command == "search" {
            let sources = (config["sources"] as? [String]) ?? []
            if sources.contains("x") && xToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return "Cannot start search: X is selected, but no X bearer token is saved. Open Settings, enter the token, and try again."
            }
            let translate = (config["translate_posts"] as? Bool) ?? true
            let infer = (config["infer_locations"] as? Bool) ?? true
            let translatedTerms = !((config["translate_term_languages"] as? [String]) ?? []).isEmpty
            if (translate || infer || translatedTerms) && llmKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return "Cannot start search: AI translation/location enrichment is enabled, but no LLM API key is saved. Add one in Settings or disable AI enrichment."
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

    private func refreshLog(from url: URL, command: String) {
        guard let data = try? Data(contentsOf: url),
              let raw = String(data: data, encoding: .utf8) else { return }
        rawBackendLog = raw
        let rendered = Self.renderBackendLog(raw)
        let header = "Starting \(command)…\n\(Self.appDiagnostics())"
        log = rendered.isEmpty ? header : header + "\n" + rendered
        outputs = Self.outputPaths(from: raw)
    }

    func copyLog() {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(log, forType: .string)
    }

    nonisolated static func execute(
        command: String, configURL: URL, logURL: URL, secrets: BackendSecrets
    ) throws -> BackendResult {
        guard let backend = Bundle.main.resourceURL?.appendingPathComponent("sugar-bridge"),
              FileManager.default.isExecutableFile(atPath: backend.path) else {
            throw NSError(
                domain: "SUGAR", code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Bundled SUGAR backend not found or is not executable."]
            )
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

        do {
            try process.run()
        } catch {
            let backendArch = binaryArchitectures(backend)
            throw NSError(
                domain: "SUGAR", code: 2,
                userInfo: [NSLocalizedDescriptionKey:
                    "Bundled backend could not start. App architecture: \(compiledArchitecture()); backend architecture: \(backendArch). \(error.localizedDescription)"
                ]
            )
        }
        process.waitUntilExit()
        try handle.synchronize()
        let text = String(data: (try? Data(contentsOf: logURL)) ?? Data(), encoding: .utf8) ?? ""
        return BackendResult(status: process.terminationStatus, text: text)
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
