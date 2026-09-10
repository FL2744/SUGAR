import AppKit
import SwiftUI
import UniformTypeIdentifiers

enum AppSection: String, CaseIterable, Identifiable {
    case search = "Search", map = "Map", analysis = "Analysis", settings = "Settings"
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .search: "magnifyingglass"
        case .map: "map"
        case .analysis: "chart.bar.doc.horizontal"
        case .settings: "key"
        }
    }
}

struct ContentView: View {
    @EnvironmentObject var model: AppModel
    @State private var selection: AppSection? = .search
    var body: some View {
        NavigationSplitView {
            List(AppSection.allCases, selection: $selection) { item in
                Label(item.rawValue, systemImage: item.icon).tag(item)
            }.navigationTitle("SUGAR")
        } detail: {
            VStack(spacing: 0) {
                switch selection ?? .search {
                case .search: SearchView()
                case .map: MapResultsView()
                case .analysis: AnalysisView()
                case .settings: SettingsView()
                }
                Divider()
                ActivityView()
            }
        }
    }
}

struct ActivityView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Activity").font(.headline)
                Spacer()
                Button("Copy Support Log") { model.copyLog() }
                    .disabled(model.log.isEmpty)
                if model.isRunning { ProgressView().controlSize(.small) }
            }
            ScrollView {
                Text(model.log).font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
            }
            if !model.outputs.isEmpty {
                ScrollView(.horizontal) {
                    HStack {
                        Text("Outputs:")
                        ForEach(model.outputs, id: \.self) { path in
                            Button(URL(fileURLWithPath: path).lastPathComponent) { model.reveal(path) }
                        }
                    }
                }
            }
        }.padding().frame(height: 210)
    }
}

struct SearchView: View {
    @EnvironmentObject var model: AppModel
    @State private var terms = "Democracy"
    @State private var termLanguages = ""
    @State private var postLanguages = "en"
    @State private var useX = true
    @State private var useBluesky = false
    @State private var useMastodon = false
    @State private var fullArchive = false
    @State private var since = ""
    @State private var until = ""
    @State private var maxPosts = 10
    @State private var maxPages = 1
    @State private var translate = true
    @State private var infer = true
    @State private var includeReposts = false
    @State private var provider = "openai"
    @State private var modelName = "gpt-5.6-luna"
    @State private var baseURL = ""
    @State private var outputDirectory = NSHomeDirectory() + "/Documents/SUGAR"

    var body: some View {
        Form {
            Section("Sources") {
                HStack {
                    Toggle("X", isOn: $useX)
                    Toggle("Bluesky", isOn: $useBluesky)
                    Toggle("Mastodon", isOn: $useMastodon)
                }
            }
            Section("Terms and languages") {
                TextField("Search terms, comma separated", text: $terms)
                TextField("Translate terms into languages, comma separated", text: $termLanguages)
                TextField("X language codes, comma separated", text: $postLanguages)
            }
            Section("Date and depth") {
                HStack {
                    TextField("Start YYYY-MM-DD", text: $since)
                    TextField("End YYYY-MM-DD", text: $until)
                }
                HStack {
                    Stepper("Posts per query: \(maxPosts)", value: $maxPosts, in: 10...500, step: 10)
                    Stepper("Pages: \(maxPages)", value: $maxPages, in: 1...100)
                }
                Toggle("Use X full archive", isOn: $fullArchive)
            }
            Section("Enrichment") {
                HStack {
                    Toggle("Translate posts", isOn: $translate)
                    Toggle("Infer locations", isOn: $infer)
                    Toggle("Include reposts", isOn: $includeReposts)
                }
                Picker("LLM provider", selection: $provider) {
                    Text("OpenAI").tag("openai")
                    Text("Virginia Tech ARC").tag("arc")
                    Text("Custom endpoint").tag("custom")
                }
                TextField("Model", text: $modelName)
                TextField("Custom base URL", text: $baseURL)
            }
            Section("Output") {
                HStack {
                    TextField("Output folder", text: $outputDirectory)
                    Button("Choose…") { if let url = chooseDirectory() { outputDirectory = url.path } }
                }
            }
            HStack {
                Spacer()
                Button("Run Search", action: runSearch).buttonStyle(.borderedProminent)
                    .disabled(model.isRunning || (!useX && !useBluesky && !useMastodon))
            }
        }.formStyle(.grouped).navigationTitle("New Search")
    }

    private func commaList(_ value: String) -> [String] {
        value.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private func runSearch() {
        var sources: [String] = []
        if useX { sources.append("x") }
        if useBluesky { sources.append("bluesky") }
        if useMastodon { sources.append("mastodon") }
        model.run(command: "search", config: [
            "sources": sources, "terms": commaList(terms),
            "translate_term_languages": commaList(termLanguages),
            "post_languages": commaList(postLanguages),
            "x_search_mode": fullArchive ? "all" : "recent",
            "since": since, "until": until,
            "max_posts_per_query": maxPosts, "max_pages_per_query": maxPages,
            "translate_posts": translate, "infer_locations": infer,
            "include_retweets": includeReposts, "target_language": "English",
            "output_directory": outputDirectory, "mastodon_url": "https://mastodon.social",
            "llm": ["provider": provider, "model": modelName, "base_url": baseURL]
        ])
    }
}

struct MapResultsView: View {
    @EnvironmentObject var model: AppModel
    @State private var source = ""
    @State private var output = ""
    var body: some View {
        Form {
            Section("Existing results") {
                HStack {
                    TextField("CSV or XLSX file", text: $source)
                    Button("Choose…") {
                        if let url = chooseFile(["csv", "xlsx"]) {
                            source = url.path
                            output = url.deletingPathExtension().path + "_map.html"
                        }
                    }
                }
            }
            Section("Output") {
                HStack {
                    TextField("HTML map", text: $output)
                    Button("Choose…") { if let url = saveFile("html") { output = url.path } }
                }
            }
            HStack {
                Spacer()
                Button("Create Map") {
                    model.run(command: "map", config: ["source_file": source, "output_file": output])
                }.buttonStyle(.borderedProminent).disabled(source.isEmpty || model.isRunning)
            }
        }.formStyle(.grouped).navigationTitle("Map Existing Results")
    }
}

struct AnalysisView: View {
    @EnvironmentObject var model: AppModel
    @State private var source = ""
    @State private var stem = ""
    @State private var format = "both"
    var body: some View {
        Form {
            Section("Existing results") {
                HStack {
                    TextField("CSV or XLSX file", text: $source)
                    Button("Choose…") {
                        if let url = chooseFile(["csv", "xlsx"]) {
                            source = url.path
                            stem = url.deletingPathExtension().path + "_analysis"
                        }
                    }
                }
            }
            Section("Report") {
                Picker("Format", selection: $format) {
                    Text("Word").tag("docx")
                    Text("PDF").tag("pdf")
                    Text("Word and PDF").tag("both")
                }
                TextField("Output path without extension", text: $stem)
            }
            HStack {
                Spacer()
                Button("Create Analysis") {
                    model.run(command: "analysis", config: [
                        "source_file": source, "output_stem": stem, "output_format": format
                    ])
                }.buttonStyle(.borderedProminent).disabled(source.isEmpty || model.isRunning)
            }
        }.formStyle(.grouped).navigationTitle("Analyze Existing Results")
    }
}

struct SettingsView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("API credentials").font(.headline)
                Text("Credentials are stored securely in your macOS Keychain and are never written to the project folder.")
                    .font(.callout)
                    .foregroundStyle(.secondary)

                Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 14) {
                    GridRow {
                        Text("X bearer token").frame(width: 180, alignment: .leading)
                        SecureField("Enter X bearer token", text: $model.xToken)
                            .credentialFieldStyle()
                    }
                    GridRow {
                        Text("LLM API key").frame(width: 180, alignment: .leading)
                        SecureField("Enter OpenAI, ARC, or custom API key", text: $model.llmKey)
                            .credentialFieldStyle()
                    }
                    GridRow {
                        Text("Bluesky identifier").frame(width: 180, alignment: .leading)
                        TextField("handle.bsky.social", text: $model.blueskyIdentifier)
                            .credentialFieldStyle()
                    }
                    GridRow {
                        Text("Bluesky app password").frame(width: 180, alignment: .leading)
                        SecureField("Enter Bluesky app password", text: $model.blueskyPassword)
                            .credentialFieldStyle()
                    }
                    GridRow {
                        Text("Mastodon token").frame(width: 180, alignment: .leading)
                        SecureField("Enter Mastodon access token", text: $model.mastodonToken)
                            .credentialFieldStyle()
                    }
                }
                .gridColumnAlignment(.leading)
                .frame(maxWidth: .infinity)

                HStack {
                    Spacer()
                    Button("Save to Keychain") { model.saveCredentials() }
                        .buttonStyle(.borderedProminent)
                }
            }
            .padding(24)
            .frame(maxWidth: 820, alignment: .leading)
        }
        .navigationTitle("Settings")
    }
}

private extension View {
    func credentialFieldStyle() -> some View {
        self
            .textFieldStyle(.plain)
            .padding(.horizontal, 10)
            .frame(minWidth: 420, minHeight: 30)
            .background(Color(nsColor: .textBackgroundColor))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(Color(nsColor: .separatorColor), lineWidth: 1)
            )
    }
}

@MainActor func chooseFile(_ extensions: [String]) -> URL? {
    let panel = NSOpenPanel()
    panel.allowedContentTypes = extensions.compactMap { UTType(filenameExtension: $0) }
    panel.canChooseDirectories = false
    return panel.runModal() == .OK ? panel.url : nil
}

@MainActor func chooseDirectory() -> URL? {
    let panel = NSOpenPanel()
    panel.canChooseDirectories = true
    panel.canChooseFiles = false
    return panel.runModal() == .OK ? panel.url : nil
}

@MainActor func saveFile(_ extensionName: String) -> URL? {
    let panel = NSSavePanel()
    if let type = UTType(filenameExtension: extensionName) { panel.allowedContentTypes = [type] }
    return panel.runModal() == .OK ? panel.url : nil
}
