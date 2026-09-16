import AppKit
import SwiftUI
import UniformTypeIdentifiers

enum AppSection: String, CaseIterable, Identifiable {
    case welcome = "Welcome"
    case search = "Search"
    case importPublic = "Public URL Import"
    case map = "Map"
    case analysis = "Analysis"
    case settings = "Settings"

    var id: String { rawValue }
    var icon: String {
        switch self {
        case .welcome: "house"
        case .search: "magnifyingglass"
        case .importPublic: "link.badge.plus"
        case .map: "map"
        case .analysis: "chart.bar.doc.horizontal"
        case .settings: "key"
        }
    }
}

struct ContentView: View {
    @EnvironmentObject var model: AppModel
    @State private var selection: AppSection? = .welcome

    var body: some View {
        NavigationSplitView {
            List(AppSection.allCases, selection: $selection) { item in
                Label(item.rawValue, systemImage: item.icon).tag(item)
            }
            .navigationTitle("SUGAR")
        } detail: {
            VStack(spacing: 0) {
                switch selection ?? .welcome {
                case .welcome: WelcomeView(selection: $selection)
                case .search: SearchView()
                case .importPublic: PublicImportView()
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
                Text("Activity & Outputs").font(.headline)
                Spacer()
                Button("Copy Support Log") { model.copyLog() }
                    .disabled(model.log.isEmpty)
                if model.isRunning { ProgressView().controlSize(.small) }
            }
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        Text(model.log)
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Color.clear.frame(height: 1).id("activity-bottom")
                    }
                }
                .onChange(of: model.log) { _ in
                    proxy.scrollTo("activity-bottom", anchor: .bottom)
                }
            }
            if !model.outputs.isEmpty {
                ScrollView(.horizontal) {
                    HStack(spacing: 8) {
                        Text("Outputs:").font(.caption).foregroundStyle(.secondary)
                        ForEach(model.outputs, id: \.self) { path in
                            Button(URL(fileURLWithPath: path).lastPathComponent) { model.open(path) }
                            Button {
                                model.reveal(path)
                            } label: {
                                Image(systemName: "folder")
                            }
                            .help("Show in Finder")
                        }
                    }
                }
            }
        }
        .padding()
        .frame(height: 220)
    }
}

struct WelcomeView: View {
    @EnvironmentObject var model: AppModel
    @Binding var selection: AppSection?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 7) {
                    Text("SUGAR Classroom Preview")
                        .font(.largeTitle.bold())
                    Text("Collect public-source material, preserve provenance, review evidence, and create maps/reports from one shared research core.")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                    Text("This packaged app already contains its Python backend. You do not need to install Python to use the macOS app.")
                        .font(.callout.bold())
                }

                GroupBox("Start here — no credentials required") {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("These actions use bundled sample data so you can learn the workflow before configuring any API credentials.")
                            .foregroundStyle(.secondary)
                        HStack {
                            Button("Open Sample Spreadsheet") { model.openSample("example-spreadsheet.xlsx") }
                            Button("Open Sample Map") { model.openSample("example-map.html") }
                            Button("Open Sample Report") { model.openSample("example-analysis.pdf") }
                        }
                        HStack {
                            Button("Create a Map from Sample", action: createSampleMap)
                                .buttonStyle(.borderedProminent)
                                .disabled(model.isRunning)
                            Button("Create a PDF Report from Sample", action: createSampleReport)
                                .disabled(model.isRunning)
                        }
                    }
                    .padding(.vertical, 4)
                }

                GroupBox("Collect or import real public material") {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Keyword Search supports X, Bluesky, Mastodon, Bilibili, Weibo, and authorized Zhihu search. Public URL Import supports known public WeChat, Zhihu, and Douyin items without pretending those platforms offer the same search surface.")
                            .foregroundStyle(.secondary)
                        HStack {
                            Button("Keyword Search") { selection = .search }
                                .buttonStyle(.borderedProminent)
                            Button("Import Public URLs") { selection = .importPublic }
                            Button("Credentials & Settings") { selection = .settings }
                        }
                    }
                    .padding(.vertical, 4)
                }

                GroupBox("Classroom feedback") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("If anything is confusing—even if you eventually solve it—that is useful feedback. Please report the point where you hesitated rather than only crashes.")
                            .foregroundStyle(.secondary)
                        HStack {
                            Button("Read Testing Guide") { model.openSample("classroom-preview.md") }
                            Button("Report Usability Feedback") { model.openFeedback() }
                                .buttonStyle(.borderedProminent)
                        }
                        Text(AppModel.appDiagnostics())
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }
            }
            .padding(24)
            .frame(maxWidth: 900, alignment: .leading)
        }
        .navigationTitle("Welcome")
    }

    private func classroomOutputDirectory() -> URL {
        let root = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
            .appendingPathComponent("SUGAR/Classroom Preview", isDirectory: true)
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }

    private func createSampleMap() {
        guard let source = model.samplePath("example-spreadsheet.xlsx") else { return }
        let output = classroomOutputDirectory().appendingPathComponent("sample-map.html").path
        model.run(command: "map", config: ["source_file": source, "output_file": output])
    }

    private func createSampleReport() {
        guard let source = model.samplePath("example-spreadsheet.xlsx") else { return }
        let stem = classroomOutputDirectory().appendingPathComponent("sample-analysis").path
        model.run(command: "analysis", config: [
            "source_file": source,
            "output_stem": stem,
            "output_format": "pdf",
        ])
    }
}

struct SearchView: View {
    @EnvironmentObject var model: AppModel
    @State private var terms = "孔子学院"
    @State private var termLanguages: Set<String> = []
    @State private var postLanguages: Set<String> = []
    @State private var useX = false
    @State private var useBluesky = false
    @State private var useMastodon = false
    @State private var useBilibili = true
    @State private var useWeibo = false
    @State private var useZhihu = false
    @State private var fullArchive = false
    @State private var since = ""
    @State private var until = ""
    @State private var maxPosts = 10
    @State private var maxPages = 1
    @State private var translate = false
    @State private var infer = false
    @State private var includeReposts = false
    @State private var llmSelection = LLMSelection()
    @State private var baseURL = ""
    @State private var outputDirectory = NSHomeDirectory() + "/Documents/SUGAR"
    @State private var showAdvanced = false

    var body: some View {
        Form {
            Section("1. Sources") {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 145), alignment: .leading)], alignment: .leading) {
                    Toggle("X", isOn: $useX).toggleStyle(.checkbox)
                    Toggle("Bluesky", isOn: $useBluesky).toggleStyle(.checkbox)
                    Toggle("Mastodon", isOn: $useMastodon).toggleStyle(.checkbox)
                    Toggle("Bilibili", isOn: $useBilibili).toggleStyle(.checkbox)
                    Toggle("Weibo", isOn: $useWeibo).toggleStyle(.checkbox)
                    Toggle("Zhihu", isOn: $useZhihu).toggleStyle(.checkbox)
                }
                Text("Bilibili is a good credential-free starting point. Weibo search availability can vary by public/session access. Zhihu keyword search requires approved Open Platform access. WeChat and Douyin are available under Public URL Import instead of being mislabeled as keyword search.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("2. Search terms") {
                TextField("Search terms, comma separated", text: $terms)
                Text("Start small for the classroom preview: one term, about 10 records, one page.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("3. Output") {
                HStack {
                    TextField("Output folder", text: $outputDirectory)
                    Button("Choose…") {
                        if let url = chooseDirectory() { outputDirectory = url.path }
                    }
                }
            }

            DisclosureGroup("Advanced options", isExpanded: $showAdvanced) {
                VStack(alignment: .leading, spacing: 14) {
                    HStack {
                        TextField("Start YYYY-MM-DD", text: $since)
                        TextField("End YYYY-MM-DD", text: $until)
                    }
                    HStack {
                        Stepper("Posts per query: \(maxPosts)", value: $maxPosts, in: 10...500, step: 10)
                        Stepper("Pages: \(maxPages)", value: $maxPages, in: 1...100)
                    }
                    Toggle("Use X full archive", isOn: $fullArchive)
                    Toggle("Include reposts", isOn: $includeReposts)

                    LanguageCheckboxes(
                        title: "Translate search terms into",
                        hint: "Optional. Requires the selected LLM provider.",
                        options: LanguageOption.translationLanguages,
                        selection: $termLanguages
                    )
                    LanguageCheckboxes(
                        title: "X post languages",
                        hint: "Optional and applies to X only.",
                        options: LanguageOption.postLanguages,
                        selection: $postLanguages
                    )

                    HStack {
                        Toggle("Translate posts", isOn: $translate)
                        Toggle("Infer broad locations", isOn: $infer)
                    }
                    if translate || infer || !termLanguages.isEmpty {
                        Picker("LLM provider", selection: $llmSelection.provider) {
                            ForEach(LLMProvider.allCases) { provider in
                                Text(provider.title).tag(provider)
                            }
                        }
                        .pickerStyle(.menu)
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
                }
                .padding(.top, 8)
            }

            HStack {
                Spacer()
                Button("Run Search", action: runSearch)
                    .buttonStyle(.borderedProminent)
                    .disabled(model.isRunning || selectedSources.isEmpty || commaList(terms).isEmpty)
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Keyword Search")
    }

    private var selectedSources: [String] {
        var sources: [String] = []
        if useX { sources.append("x") }
        if useBluesky { sources.append("bluesky") }
        if useMastodon { sources.append("mastodon") }
        if useBilibili { sources.append("bilibili") }
        if useWeibo { sources.append("weibo") }
        if useZhihu { sources.append("zhihu") }
        return sources
    }

    private func commaList(_ value: String) -> [String] {
        value.split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private func runSearch() {
        model.run(command: "search", config: [
            "sources": selectedSources,
            "terms": commaList(terms),
            "translate_term_languages": termLanguages.sorted(),
            "post_languages": postLanguages.sorted(),
            "x_search_mode": fullArchive ? "all" : "recent",
            "since": since,
            "until": until,
            "max_posts_per_query": maxPosts,
            "max_pages_per_query": maxPages,
            "translate_posts": translate,
            "infer_locations": infer,
            "include_retweets": includeReposts,
            "target_language": "English",
            "output_directory": outputDirectory,
            "mastodon_url": "https://mastodon.social",
            "llm": llmSelection.provider.configuration(model: llmSelection.model, customBaseURL: baseURL),
        ])
    }
}

struct PublicImportView: View {
    @EnvironmentObject var model: AppModel
    @State private var source = "wechat"
    @State private var items = ""
    @State private var outputDirectory = NSHomeDirectory() + "/Documents/SUGAR"

    private let sources: [(String, String, String)] = [
        ("wechat", "WeChat Official Accounts", "Known public mp.weixin.qq.com article URLs"),
        ("zhihu", "Zhihu", "Known public question/answer/article URLs"),
        ("douyin", "Douyin", "Known public/share video URLs when the public page is accessible"),
        ("bilibili", "Bilibili", "Known public video IDs/URLs supported by the Bilibili adapter"),
        ("weibo", "Weibo", "Known public Weibo post IDs/URLs supported by the Weibo adapter"),
    ]

    var body: some View {
        Form {
            Section("1. Platform") {
                Picker("Source", selection: $source) {
                    ForEach(sources, id: \.0) { item in
                        Text(item.1).tag(item.0)
                    }
                }
                .pickerStyle(.menu)
                if let item = sources.first(where: { $0.0 == source }) {
                    Text(item.2).font(.caption).foregroundStyle(.secondary)
                }
            }

            Section("2. Public URLs / IDs") {
                TextEditor(text: $items)
                    .font(.system(.body, design: .monospaced))
                    .frame(minHeight: 150)
                Text("Enter one known public item per line. SUGAR will fail explicitly if the platform presents a login, CAPTCHA, verification, or unsupported access gate; it will not treat that as zero activity.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("3. Output") {
                HStack {
                    TextField("Output folder", text: $outputDirectory)
                    Button("Choose…") {
                        if let url = chooseDirectory() { outputDirectory = url.path }
                    }
                }
            }

            HStack {
                Spacer()
                Button("Import Public Items") { runImport() }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.isRunning || itemList.isEmpty)
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Public URL Import")
    }

    private var itemList: [String] {
        var seen = Set<String>()
        return items.split(whereSeparator: \.isNewline)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty && seen.insert($0).inserted }
    }

    private func runImport() {
        model.run(command: "import-public", config: [
            "source": source,
            "items": itemList,
            "output_directory": outputDirectory,
            "name": "\(source)_public_import",
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
                Button("Use Bundled Sample") {
                    if let path = model.samplePath("example-spreadsheet.xlsx") {
                        source = path
                        output = NSHomeDirectory() + "/Documents/SUGAR/sample_map.html"
                    }
                }
            }
            Section("Output") {
                HStack {
                    TextField("HTML map", text: $output)
                    Button("Choose…") {
                        if let url = saveFile("html") { output = url.path }
                    }
                }
            }
            HStack {
                Spacer()
                Button("Create Map") {
                    model.run(command: "map", config: ["source_file": source, "output_file": output])
                }
                .buttonStyle(.borderedProminent)
                .disabled(source.isEmpty || output.isEmpty || model.isRunning)
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Map Existing Results")
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
                Button("Use Bundled Sample") {
                    if let path = model.samplePath("example-spreadsheet.xlsx") {
                        source = path
                        stem = NSHomeDirectory() + "/Documents/SUGAR/sample_analysis"
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
                        "source_file": source,
                        "output_stem": stem,
                        "output_format": format,
                    ])
                }
                .buttonStyle(.borderedProminent)
                .disabled(source.isEmpty || stem.isEmpty || model.isRunning)
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Analyze Existing Results")
    }
}

struct SettingsView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Credentials & Settings").font(.title.bold())
                Text("Credentials are stored securely in your macOS Keychain and are never written to the project folder. Leave fields blank for sources/workflows that do not require them.")
                    .font(.callout)
                    .foregroundStyle(.secondary)

                Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 14) {
                    credentialRow("X bearer token") {
                        SecureField("Required only for X", text: $model.xToken).credentialFieldStyle()
                    }
                    credentialRow("OpenAI API key") {
                        SecureField("Optional AI enrichment", text: $model.openAIKey).credentialFieldStyle()
                    }
                    credentialRow("ARC API key") {
                        SecureField("llm.arc.vt.edu key", text: $model.arcKey).credentialFieldStyle()
                    }
                    credentialRow("Custom endpoint key") {
                        SecureField("Custom provider key", text: $model.customLLMKey).credentialFieldStyle()
                    }
                    credentialRow("Bluesky identifier") {
                        TextField("handle.bsky.social", text: $model.blueskyIdentifier).credentialFieldStyle()
                    }
                    credentialRow("Bluesky app password") {
                        SecureField("Optional", text: $model.blueskyPassword).credentialFieldStyle()
                    }
                    credentialRow("Mastodon token") {
                        SecureField("Optional", text: $model.mastodonToken).credentialFieldStyle()
                    }
                    credentialRow("Weibo session cookie") {
                        SecureField("Optional authorized existing session", text: $model.weiboCookie).credentialFieldStyle()
                    }
                    credentialRow("Zhihu Access Secret") {
                        SecureField("Required only for official keyword search", text: $model.zhihuAccessSecret).credentialFieldStyle()
                    }
                }
                .gridColumnAlignment(.leading)
                .frame(maxWidth: .infinity)

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
                    Button("Report Usability Feedback") { model.openFeedback() }
                    Spacer()
                    Button("Save to Keychain") { model.saveCredentials() }
                        .buttonStyle(.borderedProminent)
                }
                Text(AppModel.appDiagnostics())
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
            }
            .padding(24)
            .frame(maxWidth: 860, alignment: .leading)
        }
        .navigationTitle("Settings")
    }

    @ViewBuilder
    private func credentialRow<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        GridRow {
            Text(label).frame(width: 190, alignment: .leading)
            content()
        }
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
