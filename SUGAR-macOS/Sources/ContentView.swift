import AppKit
import SwiftUI
import UniformTypeIdentifiers

enum AppSection: String, CaseIterable, Identifiable {
    case research = "Research Project"
    case search = "Expert Search"
    case ingest = "Public URL"
    case map = "Map"
    case analysis = "Analysis"
    case settings = "Settings"
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .research: "doc.text.magnifyingglass"
        case .search: "magnifyingglass"
        case .ingest: "link"
        case .map: "map"
        case .analysis: "chart.bar.doc.horizontal"
        case .settings: "key"
        }
    }
}

struct ContentView: View {
    @EnvironmentObject var model: AppModel
    @State private var selection: AppSection? = .research
    var body: some View {
        NavigationSplitView {
            List(AppSection.allCases, selection: $selection) { item in
                Label(item.rawValue, systemImage: item.icon).tag(item)
            }.navigationTitle("SUGAR")
        } detail: {
            VStack(spacing: 0) {
                switch selection ?? .research {
                case .research: ResearchProjectView()
                case .search: SearchView()
                case .ingest: PublicItemView()
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

struct ResearchProjectView: View {
    @EnvironmentObject var model: AppModel

    @State private var workspace = NSHomeDirectory() + "/Documents/SUGAR/Projects/State-Research-Project"
    @State private var projectName = "State Research Project"
    @State private var question = ""
    @State private var geographies = ""
    @State private var knownEntities = ""
    @State private var targetAudiences = ""
    @State private var languages = "auto"
    @State private var since = ""
    @State private var until = ""
    @State private var collectionMode = "standard"
    @State private var useBilibili = true
    @State private var useWeibo = false
    @State private var useX = false
    @State private var useBluesky = false
    @State private var useMastodon = false
    @State private var maxPosts = 20
    @State private var maxPages = 1
    @State private var strategyReviewer = ""
    @State private var strategyReviewNote = ""
    @State private var planEditReason = ""
    @State private var importFile = ""
    @State private var importSystem = "external"
    @State private var llmSelection = LLMSelection()
    @State private var baseURL = ""
    @State private var reviewWorkbook = ""
    @State private var handoffName = "sugar-handoff"
    @State private var handoffOutput = ""
    @State private var verificationBundle = ""

    var body: some View {
        Form {
            Section("1. Project workspace") {
                Text("One portable folder keeps the question, search plan, evidence, review artifacts, lineage, and final handoff together.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                TextField("Project name", text: $projectName)
                HStack {
                    TextField("Project folder", text: $workspace)
                    Button("Choose...") {
                        if let url = chooseDirectory() { workspace = url.path }
                    }
                }
                HStack {
                    Spacer()
                    Button("Create / Open Project") {
                        model.run(command: "workspace-init", config: [
                            "workspace": cleanWorkspace,
                            "name": projectName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                ? "State Research Project"
                                : projectName.trimmingCharacters(in: .whitespacesAndNewlines),
                            "exist_ok": true,
                        ])
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.isRunning || cleanWorkspace.isEmpty)
                }
            }

            Section("2. Research question") {
                Text("Start with what you need to answer. SUGAR stores the requirement and derives an inspectable bounded search plan from it.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                TextEditor(text: $question)
                    .frame(minHeight: 72)
                    .overlay(
                        RoundedRectangle(cornerRadius: 5)
                            .stroke(Color(nsColor: .separatorColor), lineWidth: 1)
                    )
                HStack {
                    TextField("Geographies, comma separated", text: $geographies)
                    TextField("Known entities / programs", text: $knownEntities)
                }
                HStack {
                    TextField("Target audiences / stakeholder groups", text: $targetAudiences)
                    TextField("Languages, comma separated or auto", text: $languages)
                }
                HStack {
                    Picker("Depth", selection: $collectionMode) {
                        Text("Quick reconnaissance").tag("quick")
                        Text("Standard research").tag("standard")
                        Text("Deep bounded research").tag("deep")
                    }
                    .pickerStyle(.menu)
                }
                HStack {
                    TextField("Start YYYY-MM-DD (optional)", text: $since)
                    TextField("End YYYY-MM-DD (optional)", text: $until)
                }
                VStack(alignment: .leading, spacing: 8) {
                    Text("Preferred searchable sources").font(.headline)
                    HStack {
                        Toggle("Bilibili", isOn: $useBilibili)
                        Toggle("Weibo", isOn: $useWeibo)
                        Toggle("X", isOn: $useX)
                    }
                    HStack {
                        Toggle("Bluesky", isOn: $useBluesky)
                        Toggle("Mastodon", isOn: $useMastodon)
                    }
                    Text("Source preferences guide collection; they do not imply coverage. Zero-result searches and source failures remain explicit in the project record.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                HStack {
                    Spacer()
                    Button("Save Research Question", action: saveRequirement)
                        .disabled(
                            model.isRunning
                            || cleanWorkspace.isEmpty
                            || question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        )
                }
            }

            Section("2b. Interpret and approve the research strategy") {
                Text("SUGAR compiles the sentence into explicit source-span concepts, semantic interpretations, search hypotheses, missing dimensions, and operational research dimensions. AI semantic expansion is optional and cannot turn a hypothesis into an analyst-stated fact.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                HStack {
                    Button("Compile Deterministically") {
                        compileStrategy(useAI: false)
                    }
                    .buttonStyle(.borderedProminent)
                    Button("Compile + AI") {
                        compileStrategy(useAI: true)
                    }
                    Button("Refresh Interpretation") {
                        model.run(
                            command: "research-strategy-review",
                            config: ["workspace": cleanWorkspace]
                        )
                    }
                    Spacer()
                }
                .disabled(model.isRunning || cleanWorkspace.isEmpty)

                TextField("Analytic task", text: $model.researchStrategyTask)
                if model.researchStrategyConcepts.isEmpty {
                    Text("Compile the saved research question to see how SUGAR interpreted it.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach($model.researchStrategyConcepts) { $concept in
                        GroupBox {
                            VStack(alignment: .leading, spacing: 7) {
                                HStack {
                                    Text(concept.origin.uppercased())
                                        .font(.caption.bold())
                                    Text(concept.kind)
                                        .font(.caption)
                                    Text(String(format: "%.2f", concept.confidence))
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    Toggle("Use", isOn: $concept.included)
                                        .toggleStyle(.checkbox)
                                }
                                if concept.origin == "explicit" {
                                    Text(concept.value)
                                        .textSelection(.enabled)
                                    if !concept.sourceText.isEmpty {
                                        Text("Exact source span: \"\(concept.sourceText)\"")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                } else {
                                    TextField("Concept value", text: $concept.value)
                                }
                                TextField("Rationale", text: $concept.rationale)
                            }
                        } label: {
                            Text(concept.value)
                        }
                    }
                }
                if !model.researchStrategyDimensions.isEmpty {
                    Text("Research dimensions")
                        .font(.headline)
                    ForEach($model.researchStrategyDimensions) { $dimension in
                        GroupBox {
                            VStack(alignment: .leading, spacing: 7) {
                                HStack {
                                    Text(dimension.name)
                                        .font(.caption.bold())
                                    Spacer()
                                    Toggle("Use", isOn: $dimension.included)
                                        .toggleStyle(.checkbox)
                                }
                                TextField("Operational question", text: $dimension.question)
                                TextField("Indicators, comma separated", text: $dimension.indicators)
                                TextField("Source families, comma separated", text: $dimension.sourceFamilies)
                                TextField("Rationale", text: $dimension.rationale)
                            }
                        } label: {
                            Text(dimension.name)
                        }
                    }
                }
                if !model.researchStrategySummary.isEmpty {
                    Text(model.researchStrategySummary)
                        .font(.caption)
                        .textSelection(.enabled)
                }
                HStack {
                    TextField("Named analyst reviewer", text: $strategyReviewer)
                    TextField("Optional review note", text: $strategyReviewNote)
                }
                HStack {
                    Text("State: \(model.researchStrategyReviewState.isEmpty ? "not compiled" : model.researchStrategyReviewState)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Button("Save Interpretation Edits") {
                        saveStrategy(decision: "")
                    }
                    Button("Approve Research Strategy") {
                        saveStrategy(decision: "approved")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(strategyReviewer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    Button("Build Search Plan from Approved Strategy") {
                        model.run(command: "research-plan", config: ["workspace": cleanWorkspace])
                    }
                }
                .disabled(model.isRunning || cleanWorkspace.isEmpty)
            }

            Section("2c. Review search branches") {
                Text("Review the generated plan before collection. Edit a query or rationale directly, then save it or record an approval, pause, or exclusion. Every change is appended to the plan audit history.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                HStack {
                    TextField("Optional analyst reason", text: $planEditReason)
                    Button("Refresh Plan") {
                        model.run(
                            command: "research-plan-review",
                            config: ["workspace": cleanWorkspace]
                        )
                    }
                    .disabled(model.isRunning || cleanWorkspace.isEmpty)
                }
                if model.researchPlanBranches.isEmpty {
                    Text("Build or refresh a search plan to review its branches.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach($model.researchPlanBranches) { $branch in
                        GroupBox {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text(branch.origin.capitalized)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text("Status: \(branch.status)")
                                        .font(.caption)
                                    Text("Hop: \(branch.hopDepth)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    Text(branch.branchID)
                                        .font(.system(.caption2, design: .monospaced))
                                        .foregroundStyle(.secondary)
                                }
                                TextField("Query", text: $branch.query)
                                TextField("Rationale", text: $branch.rationale)
                                HStack {
                                    Button("Save Edits") {
                                        updatePlanBranch(branch)
                                    }
                                    Button("Approve") {
                                        updatePlanBranch(branch, status: "approved")
                                    }
                                    Button("Pause") {
                                        updatePlanBranch(branch, status: "paused")
                                    }
                                    Button("Exclude") {
                                        updatePlanBranch(branch, status: "excluded")
                                    }
                                    Spacer()
                                }
                                .disabled(model.isRunning)
                            }
                        } label: {
                            Text(branch.query)
                        }
                    }
                }
            }

            Section("3. Gather and review evidence") {
                HStack {
                    Stepper("Posts per query: \(maxPosts)", value: $maxPosts, in: 1...1000)
                    Stepper("Pages per query: \(maxPages)", value: $maxPages, in: 1...100)
                }
                HStack {
                    Spacer()
                    Button("Run Search Plan", action: collectPlan)
                        .buttonStyle(.borderedProminent)
                        .disabled(model.isRunning || cleanWorkspace.isEmpty || selectedSources.isEmpty)
                }

                Divider()
                Text("Or import an existing authorized partner / Department dataset. Imported and collected material use the same evidence and provenance model.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                HStack {
                    TextField("Existing CSV / JSONL", text: $importFile)
                    Button("Choose...") {
                        if let url = chooseFile(["csv", "jsonl"]) { importFile = url.path }
                    }
                }
                TextField("Source system", text: $importSystem)
                HStack {
                    Spacer()
                    Button("Import Existing Dataset") {
                        model.run(command: "research-import", config: [
                            "workspace": cleanWorkspace,
                            "source_file": importFile,
                            "source_system": importSystem.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                ? "external"
                                : importSystem.trimmingCharacters(in: .whitespacesAndNewlines),
                        ])
                    }
                    .disabled(model.isRunning || cleanWorkspace.isEmpty || importFile.isEmpty)
                }

                Divider()
                Text("Prepare unreviewed, source-grounded observations and blank State assessments for human review without an AI key. Existing review files are never overwritten.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Prepare Manual Review (no AI key)") {
                    model.run(command: "research-prepare-review", config: ["workspace": cleanWorkspace])
                }
                .disabled(model.isRunning || cleanWorkspace.isEmpty)

                Divider()
                Picker("Triage LLM provider", selection: $llmSelection.provider) {
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
                HStack {
                    Spacer()
                    Button("Triage into ResearchObservations") {
                        model.run(command: "research-triage", config: [
                            "workspace": cleanWorkspace,
                            "continue_on_error": true,
                            "llm": llmSelection.provider.configuration(
                                model: llmSelection.model,
                                customBaseURL: baseURL
                            ),
                        ])
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.isRunning || cleanWorkspace.isEmpty)
                    Button("Apply Evidence Feedback to Plan") {
                        model.run(command: "research-feedback", config: ["workspace": cleanWorkspace])
                    }
                    .disabled(model.isRunning || cleanWorkspace.isEmpty)
                }
            }

            Section("4. Human review and verified handoff") {
                Text("Manual drafts and AI suggestions remain unverified until a named analyst reviews the underlying evidence and any analytic claims. Export one review workbook, make the human decisions, save it, and apply them through SUGAR's verification gates.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                HStack {
                    Button("Prepare State Assessment Suggestions") {
                        model.run(command: "state-triage", config: [
                            "workspace": cleanWorkspace,
                            "llm": llmSelection.provider.configuration(
                                model: llmSelection.model,
                                customBaseURL: baseURL
                            ),
                        ])
                    }
                    .disabled(model.isRunning || cleanWorkspace.isEmpty)
                    Button("Export Human Review Workbook") {
                        model.run(
                            command: "state-review-export",
                            config: ["workspace": cleanWorkspace]
                        )
                    }
                    .disabled(model.isRunning || cleanWorkspace.isEmpty)
                    Spacer()
                }
                HStack {
                    TextField("Completed review workbook (optional override)", text: $reviewWorkbook)
                    Button("Choose...") {
                        if let url = chooseFile(["xlsx"]) { reviewWorkbook = url.path }
                    }
                    Button("Apply Human Review") {
                        applyHumanReview()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.isRunning || cleanWorkspace.isEmpty)
                }
                Text("Leave the workbook field blank to reuse the project's latest exported review workbook after editing and saving it. The workbook carries observation, assessment, claim, sponsor-support, and source-conflict review fields when available.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Divider()
                Text("After review, export a portable bundle containing the requirement, search plan, evidence, reviewed observations, limitations, provenance, assessments, source conflicts, and claim/evidence lineage when available.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                TextField("Handoff name", text: $handoffName)
                HStack {
                    TextField("Optional handoff parent folder", text: $handoffOutput)
                    Button("Choose...") {
                        if let url = chooseDirectory() { handoffOutput = url.path }
                    }
                }
                HStack {
                    Spacer()
                    Button("Export Verified Handoff", action: exportHandoff)
                        .buttonStyle(.borderedProminent)
                        .disabled(model.isRunning || cleanWorkspace.isEmpty)
                }

                Divider()
                HStack {
                    TextField("Existing handoff bundle to verify", text: $verificationBundle)
                    Button("Choose...") {
                        if let url = chooseDirectory() { verificationBundle = url.path }
                    }
                    Button("Verify Bundle") {
                        model.run(command: "research-handoff-verify", config: [
                            "bundle_directory": verificationBundle
                        ])
                    }
                    .disabled(model.isRunning || verificationBundle.isEmpty)
                }
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Research Project")
    }

    private var cleanWorkspace: String {
        workspace.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var selectedSources: [String] {
        var result: [String] = []
        if useBilibili { result.append("bilibili") }
        if useWeibo { result.append("weibo") }
        if useX { result.append("x") }
        if useBluesky { result.append("bluesky") }
        if useMastodon { result.append("mastodon") }
        return result
    }

    private func commaList(_ value: String) -> [String] {
        value.split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private func saveRequirement() {
        model.run(command: "research-requirement", config: [
            "workspace": cleanWorkspace,
            "question": question.trimmingCharacters(in: .whitespacesAndNewlines),
            "geographies": commaList(geographies),
            "known_entities": commaList(knownEntities),
            "target_audiences": commaList(targetAudiences),
            "languages": commaList(languages),
            "since": since.trimmingCharacters(in: .whitespacesAndNewlines),
            "until": until.trimmingCharacters(in: .whitespacesAndNewlines),
            "collection_mode": collectionMode,
            "preferred_sources": selectedSources,
        ])
    }

    private func collectPlan() {
        model.run(command: "research-collect", config: [
            "workspace": cleanWorkspace,
            "sources": selectedSources,
            "max_posts_per_query": maxPosts,
            "max_pages_per_query": maxPages,
            "continue_on_source_error": true,
        ])
    }

    private func compileStrategy(useAI: Bool) {
        var config: [String: Any] = [
            "workspace": cleanWorkspace,
            "ai_expand": useAI,
        ]
        if useAI {
            config["llm"] = llmSelection.provider.configuration(
                model: llmSelection.model,
                customBaseURL: baseURL
            )
        }
        model.run(command: "research-compile", config: config)
    }

    private func saveStrategy(decision: String) {
        let updates: [[String: Any]] = model.researchStrategyConcepts.map { concept in
            var item: [String: Any] = [
                "concept_id": concept.conceptID,
                "included": concept.included,
                "rationale": concept.rationale,
            ]
            if concept.origin != "explicit" {
                item["value"] = concept.value
            }
            return item
        }
        let dimensionUpdates: [[String: Any]] = model.researchStrategyDimensions.map { dimension in
            [
                "dimension_id": dimension.dimensionID,
                "included": dimension.included,
                "question": dimension.question,
                "indicators": commaList(dimension.indicators),
                "source_families": commaList(dimension.sourceFamilies),
                "rationale": dimension.rationale,
            ]
        }
        var config: [String: Any] = [
            "workspace": cleanWorkspace,
            "actor": strategyReviewer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? "desktop analyst"
                : strategyReviewer.trimmingCharacters(in: .whitespacesAndNewlines),
            "analytic_task": model.researchStrategyTask,
            "concept_updates": updates,
            "dimension_updates": dimensionUpdates,
        ]
        if !decision.isEmpty {
            config["decision"] = decision
            config["reviewer"] = strategyReviewer.trimmingCharacters(in: .whitespacesAndNewlines)
            config["review_note"] = strategyReviewNote.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        model.run(command: "research-strategy-update", config: config)
    }

    private func updatePlanBranch(
        _ branch: ResearchPlanBranchView,
        status: String = ""
    ) {
        var config: [String: Any] = [
            "workspace": cleanWorkspace,
            "branch_id": branch.branchID,
            "query": branch.query,
            "rationale": branch.rationale,
            "actor": "desktop analyst",
            "reason": planEditReason.trimmingCharacters(in: .whitespacesAndNewlines),
        ]
        if !status.isEmpty { config["status"] = status }
        model.run(command: "research-plan-update", config: config)
    }

    private func applyHumanReview() {
        var config: [String: Any] = ["workspace": cleanWorkspace]
        let workbook = reviewWorkbook.trimmingCharacters(in: .whitespacesAndNewlines)
        if !workbook.isEmpty { config["workbook"] = workbook }
        model.run(command: "state-review-apply", config: config)
    }

    private func exportHandoff() {
        var config: [String: Any] = [
            "workspace": cleanWorkspace,
            "name": handoffName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? "sugar-handoff"
                : handoffName.trimmingCharacters(in: .whitespacesAndNewlines),
            "create_zip": true,
        ]
        let output = handoffOutput.trimmingCharacters(in: .whitespacesAndNewlines)
        if !output.isEmpty { config["output_directory"] = output }
        model.run(command: "research-handoff", config: config)
    }
}

private struct PublicItemSource: Identifiable {
    let label: String
    let value: String
    var id: String { value }
}

struct PublicItemView: View {
    @EnvironmentObject var model: AppModel
    @State private var source = "wechat"
    @State private var identifier = ""
    @State private var query = ""
    @State private var outputDirectory = NSHomeDirectory() + "/Documents/SUGAR"

    private let sources = [
        PublicItemSource(label: "WeChat Official Account article", value: "wechat"),
        PublicItemSource(label: "Bilibili video", value: "bilibili"),
        PublicItemSource(label: "Weibo post", value: "weibo"),
    ]

    var body: some View {
        Form {
            Section("Known public item") {
                Picker("Source", selection: $source) {
                    ForEach(sources) { item in
                        Text(item.label).tag(item.value)
                    }
                }
                TextField("Public URL or supported native item ID", text: $identifier)
                TextField("Optional research query / provenance label", text: $query)
                HStack {
                    TextField("Output folder", text: $outputDirectory)
                    Button("Choose…") { if let url = chooseDirectory() { outputDirectory = url.path } }
                }
                Text("WeChat currently supports ordinary public mp.weixin.qq.com Official Account articles. SUGAR does not search private WeChat, manufacture login state, solve challenges, or bypass access controls.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            HStack {
                Spacer()
                Button("Import Public Item") {
                    model.run(command: "ingest", config: [
                        "source": source,
                        "identifier": identifier.trimmingCharacters(in: .whitespacesAndNewlines),
                        "query": query.trimmingCharacters(in: .whitespacesAndNewlines),
                        "output_directory": outputDirectory,
                    ])
                }
                .buttonStyle(.borderedProminent)
                .disabled(model.isRunning || identifier.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .formStyle(.grouped)
        .navigationTitle("Public URL")
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
                if model.isRunning {
                    ProgressView().controlSize(.small)
                    Button("Cancel") { model.cancel() }
                }
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
                                .help(path)
                                .contextMenu {
                                    Button("Copy path") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(path, forType: .string) }
                                }
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
        var seen = Set<String>()
        return value.split(whereSeparator: { $0 == "," || $0.isNewline })
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty && seen.insert($0.lowercased()).inserted }
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
