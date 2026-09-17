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
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        Text(model.log).font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                        Color.clear.frame(height: 1).id("activity-bottom")
                    }
                }
                .onChange(of: model.log) { _ in
                    proxy.scrollTo("activity-bottom", anchor: .bottom)
                }
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
    @State private var terms = ""
    @State private var termLanguages: Set<String> = []
    @State private var postLanguages: Set<String> = []
    @State private var useBilibili = true
    @State private var useWeibo = false
    @State private var useX = false
    @State private var useBluesky = false
    @State private var useMastodon = false
    @State private var fullArchive = false
    @State private var since = ""
    @State private var until = ""
    @State private var maxPosts = 20
    @State private var maxPages = 1
    @State private var translate = false
    @State private var infer = false
    @State private var includeReposts = false
    @State private var llmSelection = LLMSelection()
    @State private var baseURL = ""
    @State private var outputDirectory = NSHomeDirectory() + "/Documents/SUGAR"

    var body: some View {
        Form {
            Section("Sources") {
                HStack {
                    Toggle("Bilibili", isOn: $useBilibili)
                    Toggle("Weibo", isOn: $useWeibo)
                    Toggle("X", isOn: $useX)
                }
                HStack {
                    Toggle("Bluesky", isOn: $useBluesky)
                    Toggle("Mastodon", isOn: $useMastodon)
                }
                Text("Bilibili uses bounded anonymous public search when available. Weibo keyword search requires an authorized session saved in Settings.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Section("Terms and languages") {
                TextField("Search terms, comma separated", text: $terms)
                LanguageCheckboxes(
                    title: "Translate search terms into",
                    hint: "Leave unchecked to use only your original search terms.",
                    options: LanguageOption.translationLanguages,
                    selection: $termLanguages
                )
                LanguageCheckboxes(
                    title: "X post languages",
                    hint: "Leave unchecked to include posts in all languages. Applies to X only.",
                    options: LanguageOption.postLanguages,
                    selection: $postLanguages
                )
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
                Picker("LLM provider", selection: $llmSelection.provider) {
                    ForEach(LLMProvider.allCases) { provider in
                        Text(provider.title).tag(provider)
                    }
                }.pickerStyle(.menu)
                if llmSelection.provider == .custom {
                    TextField("Model ID", text: $llmSelection.model)
                    TextField("Custom base URL", text: $baseURL)
                } else {
                    Picker("Model", selection: $llmSelection.model) {
                        ForEach(llmSelection.provider.models, id: \.self) { name in
                            Text(name).tag(name)
                        }
                    }
                    .pickerStyle(.menu)
                    .id(llmSelection.provider)
                }
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
                    .disabled(
                        model.isRunning
                        || terms.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        || (!useBilibili && !useWeibo && !useX && !useBluesky && !useMastodon)
                    )
            }
        }.formStyle(.grouped).navigationTitle("New Search")
    }

    private func commaList(_ value: String) -> [String] {
        value.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private func runSearch() {
        var sources: [String] = []
        if useBilibili { sources.append("bilibili") }
        if useWeibo { sources.append("weibo") }
        if useX { sources.append("x") }
        if useBluesky { sources.append("bluesky") }
        if useMastodon { sources.append("mastodon") }
        model.run(command: "search", config: [
            "sources": sources, "terms": commaList(terms),
            "translate_term_languages": termLanguages.sorted(),
            "post_languages": postLanguages.sorted(),
            "x_search_mode": fullArchive ? "all" : "recent",
            "since": since, "until": until,
            "max_posts_per_query": maxPosts, "max_pages_per_query": maxPages,
            "translate_posts": translate, "infer_locations": infer,
            "include_retweets": includeReposts, "target_language": "English",
            "bilibili_hydrate_details": false,
            "output_directory": outputDirectory, "mastodon_url": "https://mastodon.social",
            "llm": llmSelection.provider.configuration(model: llmSelection.model, customBaseURL: baseURL)
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
                        Text("OpenAI API key").frame(width: 180, alignment: .leading)
                        SecureField("Enter OpenAI API key", text: $model.openAIKey)
                            .credentialFieldStyle()
                    }
                    GridRow {
                        Text("ARC API key").frame(width: 180, alignment: .leading)
                        SecureField("Enter llm.arc.vt.edu API key", text: $model.arcKey)
                            .credentialFieldStyle()
                    }
                    GridRow {
                        Text("Custom endpoint key").frame(width: 180, alignment: .leading)
                        SecureField("Enter custom endpoint API key", text: $model.customLLMKey)
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
                    GridRow {
                        Text("Weibo session").frame(width: 180, alignment: .leading)
                        SecureField("Authorized Weibo cookie for keyword search", text: $model.weiboCookie)
                            .credentialFieldStyle()
                    }
                }
                .gridColumnAlignment(.leading)
                .frame(maxWidth: .infinity)

                GroupBox("Virginia Tech ARC quick setup") {
                VStack(alignment: .leading, spacing: 9) {
                    Text("ARC's shared hosted-model API is available to Virginia Tech students, faculty, and staff without a separate ARC HPC account. Your personal API key stays in SUGAR's Keychain storage.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                    Link("1. Get ARC API Key", destination: URL(string: "https://llm.arc.vt.edu")!)
                    Text("2. In ARC: User profile → Settings → Account → API keys. Create a personal key and paste it into the ARC API key field above.")
                        .font(.callout)
                    Text("3. Test the connection below. Then choose Virginia Tech ARC as the LLM provider in Search; gpt-oss-120b is the default classroom model.")
                        .font(.callout)
                    Button("3. Test ARC Connection") {
                        model.run(command: "llm-check", config: [
                            "llm": LLMProvider.arc.configuration(model: "gpt-oss-120b", customBaseURL: "")
                        ])
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.arcKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isRunning)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(4)
            }

                if !model.legacyLLMKey.isEmpty {
                    HStack {
                        Text("A key from the previous shared field is saved. Choose which provider it belongs to.")
                            .font(.callout)
                        Menu("Use previous key for…") {
                            ForEach(LLMProvider.allCases) { provider in
                                Button(provider.title) { model.assignPreviousKey(to: provider) }
                            }
                        }
                    }
                }
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


private struct LanguageOption: Identifiable {
    let name: String
    let value: String
    var id: String { value }

    // Match the named language choices in the Python backend.
    static let postLanguages: [LanguageOption] = [
        .init(name: "Arabic", value: "ar"),
        .init(name: "Chinese", value: "zh"),
        .init(name: "English", value: "en"),
        .init(name: "French", value: "fr"),
        .init(name: "German", value: "de"),
        .init(name: "Hindi", value: "hi"),
        .init(name: "Indonesian", value: "id"),
        .init(name: "Italian", value: "it"),
        .init(name: "Japanese", value: "ja"),
        .init(name: "Korean", value: "ko"),
        .init(name: "Portuguese", value: "pt"),
        .init(name: "Russian", value: "ru"),
        .init(name: "Spanish", value: "es"),
        .init(name: "Turkish", value: "tr"),
    ]

    static let translationLanguages: [LanguageOption] = (
        postLanguages.filter { $0.value != "zh" }.map {
            LanguageOption(name: $0.name, value: $0.name)
        } + [
            .init(name: "Simplified Chinese", value: "Simplified Chinese"),
            .init(name: "Traditional Chinese", value: "Traditional Chinese"),
        ]
    ).sorted { $0.name < $1.name }
}

private struct LanguageCheckboxes: View {
    let title: String
    let hint: String
    let options: [LanguageOption]
    @Binding var selection: Set<String>

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(title).font(.headline)
                Spacer()
                Button("Clear selection") { selection.removeAll() }
                    .disabled(selection.isEmpty)
            }
            Text(hint).font(.caption).foregroundStyle(.secondary)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 165), alignment: .leading)],
                      alignment: .leading, spacing: 8) {
                ForEach(options) { language in
                    Toggle(language.name, isOn: Binding(
                        get: { selection.contains(language.value) },
                        set: { checked in
                            if checked { selection.insert(language.value) }
                            else { selection.remove(language.value) }
                        }
                    ))
                    .toggleStyle(.checkbox)
                }
            }
        }
        .padding(.vertical, 6)
    }
}
