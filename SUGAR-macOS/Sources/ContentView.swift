import AppKit
import SwiftUI
import UniformTypeIdentifiers

enum AppSection: String, CaseIterable, Identifiable {
    case research = "Research Project"
    case workspace = "Research Workspace"
    case search = "Expert Search"
    case ingest = "Public URL"
    case map = "Map"
    case analysis = "Analysis"
    case settings = "Settings"
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .research: "doc.text.magnifyingglass"
        case .workspace: "square.stack.3d.up"
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
    @AppStorage("sugar.workspace.autoMonitoring") private var automaticMonitoring = false
    var body: some View {
        NavigationSplitView {
            List(AppSection.allCases, selection: $selection) { item in
                Label(item.rawValue, systemImage: item.icon).tag(item)
            }.navigationTitle("SUGAR")
        } detail: {
            VStack(spacing: 0) {
                switch selection ?? .research {
                case .research: ResearchProjectView(workspace: $model.activeWorkspace)
                case .workspace: WorkspaceHubView()
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
        .task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 60_000_000_000)
                let manifest = URL(fileURLWithPath: model.activeWorkspace).appendingPathComponent("sugar-project.json")
                if automaticMonitoring && !model.isRunning && FileManager.default.fileExists(atPath: manifest.path) {
                    model.run(command: "workspace-hub", config: ["action": "monitor-run-due", "workspace": model.activeWorkspace, "max_monitors": 25])
                }
            }
        }
    }
}

struct WorkspaceHubView: View {
    @EnvironmentObject var model: AppModel
    @AppStorage("sugar.workspace.autoMonitoring") private var automaticMonitoring = false
    @AppStorage("sugar.workspace.analystName") private var analystName = "analyst"
    @State private var projectRoot = ""
    @State private var projectName = "State Research Project"
    @State private var subprojectName = ""
    @State private var bundleFile = ""
    @State private var bundleDestination = ""
    @State private var linkImportedChild = true
    @State private var registryFile = ""
    @State private var registryTemplate = "american_spaces"
    @State private var registryMapping = "{}"
    @State private var registryDatasetName = ""
    @State private var registryNetwork = ""
    @State private var registryScope = ""
    @State private var registryLimits = ""
    @State private var registryLicense = ""
    @State private var registryAcceptPartial = false
    @State private var registryQuery = ""
    @State private var registryStatus = ""
    @State private var compareLeftID = ""
    @State private var compareRightID = ""
    @State private var comparisonCoverageDocumented = false
    @State private var registryEntityJSON = "{\n  \"name\": \"\",\n  \"entity_type\": \"institution\",\n  \"network\": \"\",\n  \"status\": \"unknown\"\n}"
    @State private var registryEvidenceURL = ""
    @State private var registryReviewState = "unreviewed"
    @State private var relationshipSourceID = ""
    @State private var relationshipTargetID = ""
    @State private var relationshipType = "partner_of"
    @State private var relationshipEvidenceURL = ""
    @State private var mapSourceFile = ""
    @State private var mapLayers = ""
    @State private var mapAsOfDate = ""
    @State private var monitorName = ""
    @State private var monitorTerms = ""
    @State private var monitorTargets = ""
    @State private var monitorSources = "bilibili"
    @State private var monitorGeographies = ""
    @State private var monitorCadence = 1440.0
    @State private var selectedMonitorID = ""
    @State private var selectedMaterialID = ""
    @State private var reviewNote = ""
    @State private var conversationFile = ""
    @State private var conversationID = ""
    @State private var dataFile = ""
    @State private var dataFilterColumn = ""
    @State private var dataFilterValue = ""

    private var projectRows: [[String: Any]] {
        model.workspaceHubResults["project-list"] as? [[String: Any]] ?? []
    }
    private var registryRows: [[String: Any]] {
        (model.workspaceHubResults["registry-list"] as? [String: Any])?["entities"] as? [[String: Any]] ?? []
    }
    private var monitorRows: [[String: Any]] {
        model.workspaceHubResults["monitor-list"] as? [[String: Any]] ?? []
    }
    private var materialRows: [[String: Any]] {
        (model.workspaceHubResults["monitor-feed"] as? [String: Any])?["material"] as? [[String: Any]] ?? []
    }
    private var dataRows: [[String: Any]] {
        (model.workspaceHubResults["dataset-browse"] as? [String: Any])?["rows"] as? [[String: Any]] ?? []
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                GroupBox("Active project") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Projects preserve evidence, provenance, saved searches, annotations, reference data, maps, review states, and history. Subprojects keep their own research tracks.")
                            .font(.caption).foregroundStyle(.secondary)
                        HStack {
                            TextField("SUGAR project folder", text: $model.activeWorkspace)
                            Button("Choose…") { if let url = chooseDirectory() { model.activeWorkspace = url.path } }
                        }
                        HStack {
                            TextField("Project name for a new folder", text: $projectName)
                            Button("Create / open") { createOrOpenProject() }.buttonStyle(.borderedProminent)
                            Button("Dashboard") { hub("dashboard") }
                        }
                        TextField("Analyst name recorded in review history", text: $analystName)
                    }
                }

                TabView {
                    projectsTab.tabItem { Label("Projects", systemImage: "folder") }
                    registryTab.tabItem { Label("Registry", systemImage: "building.2") }
                    dataTab.tabItem { Label("Data", systemImage: "tablecells") }
                    mapTab.tabItem { Label("Maps", systemImage: "map") }
                    monitoringTab.tabItem { Label("Listening posts", systemImage: "dot.radiowaves.left.and.right") }
                    conversationHelpTab.tabItem { Label("Conversations & help", systemImage: "text.bubble") }
                }
                .frame(minHeight: 690)
            }
            .padding(20)
            .frame(maxWidth: 1100, alignment: .leading)
        }
        .navigationTitle("Research Workspace")
        .onChange(of: model.workspaceHubRevision) { _ in
            if model.workspaceHubAction == "registry-preview",
               let preview = model.workspaceHubResults["registry-preview"] as? [String: Any],
               let mapping = preview["suggested_mapping"], let text = Self.prettyJSON(mapping) {
                registryMapping = text
                if registryDatasetName.isEmpty { registryDatasetName = URL(fileURLWithPath: registryFile).deletingPathExtension().lastPathComponent }
            } else if model.workspaceHubAction == "registry-template",
                      let template = model.workspaceHubResults["registry-template"] as? [String: Any] {
                registryFile = template["path"] as? String ?? registryFile
                registryDatasetName = URL(fileURLWithPath: registryFile).deletingPathExtension().lastPathComponent
                registryNetwork = template["network"] as? String ?? registryNetwork
            }
        }
    }

    private var projectsTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                GroupBox("Project browser") {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            TextField("Folder containing projects", text: $projectRoot)
                            Button("Choose…") { if let url = chooseDirectory() { projectRoot = url.path } }
                            Button("Find projects") { hub("project-list", ["projects_root": projectRoot]) }.buttonStyle(.borderedProminent)
                        }
                        if projectRows.isEmpty {
                            Text("No project list loaded yet.").foregroundStyle(.secondary)
                        }
                        ForEach(Array(projectRows.enumerated()), id: \.offset) { entry in
                            let row = entry.element
                            Button {
                                let path = row["root"] as? String ?? ""
                                guard !path.isEmpty else { return }
                                model.activeWorkspace = path
                                hub("dashboard")
                            } label: {
                                HStack {
                                    VStack(alignment: .leading) {
                                        Text(row["name"] as? String ?? "SUGAR project").fontWeight(.semibold)
                                        Text(row["root"] as? String ?? "").font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Text("\(row["artifact_count"] as? Int ?? 0) artifacts · \(row["child_count"] as? Int ?? 0) subprojects")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }.buttonStyle(.plain)
                        }
                        if let dashboard = model.workspaceHubResults["dashboard"] as? [String: Any] {
                            Text("\(dashboard["name"] as? String ?? "") · \(dashboard["artifact_count"] as? Int ?? 0) artifacts · \(dashboard["pending_review"] as? Int ?? 0) pending review · last activity \(dashboard["last_activity"] as? String ?? "unknown")")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }

                GroupBox("Subprojects and reproducible history") {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            TextField("Country, network, or institution research track", text: $subprojectName)
                            Button("Create subproject") {
                                guard !subprojectName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
                                hub("project-create-subproject", ["name": subprojectName, "description": "Research subproject"])
                            }
                        }
                        HStack {
                            Button("Load project history") { hub("project-history", ["limit": 500]) }
                            Button("Rerun latest search") { rerunLatestSearch() }
                        }
                        TextEditor(text: .constant(model.workspaceHubResults["project-history"].flatMap(Self.prettyJSON) ?? "Project history includes query terms, source platforms, date filters, source coverage, result counts, outputs, and research-plan changes."))
                            .font(.system(.caption, design: .monospaced))
                            .frame(minHeight: 210)
                    }
                }

                GroupBox("Portable project sharing") {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Button("Export bundle…") {
                                guard let url = saveFile("zip") else { return }
                                hub("project-export", ["output_file": url.path])
                            }
                            Button("Choose bundle…") { if let url = chooseFile(["zip"]) { bundleFile = url.path } }
                            Text(bundleFile).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                        HStack {
                            TextField("New import destination folder", text: $bundleDestination)
                            Button("Choose destination parent…") { if let url = chooseDirectory() { bundleDestination = url.appendingPathComponent("Imported SUGAR Project").path } }
                        }
                        Toggle("Link imported project as a subproject of the active project", isOn: $linkImportedChild)
                        Button("Import bundle into new folder") {
                            guard !bundleFile.isEmpty, !bundleDestination.isEmpty else { return }
                            var values: [String: Any] = ["bundle": bundleFile, "destination": bundleDestination]
                            if linkImportedChild { values["parent_workspace"] = model.activeWorkspace }
                            hub("project-import", values)
                        }.disabled(bundleFile.isEmpty || bundleDestination.isEmpty)
                        Text("To link the imported project, choose a destination inside the active project folder. Bundles exclude credentials and verify file hashes before import.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }.padding(12)
        }
    }

    private var registryTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                GroupBox("Institution and program reference registry") {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            TextField("Search name, alias, city, or country", text: $registryQuery)
                            TextField("Network", text: $registryNetwork)
                            Picker("Status", selection: $registryStatus) {
                                Text("All").tag("")
                                ForEach(["active", "closed", "renamed", "relocated", "unknown"], id: \.self) { Text($0.capitalized).tag($0) }
                            }.frame(width: 130)
                            Button("Load") { loadRegistry() }.buttonStyle(.borderedProminent)
                            Button("Export CSV") {
                                guard let url = saveFile("csv") else { return }
                                hub("registry-export", ["output_file": url.path, "format": "csv"])
                            }
                        }
                        ForEach(Array(registryRows.enumerated()), id: \.offset) { entry in
                            let row = entry.element
                            VStack(alignment: .leading, spacing: 3) {
                                Text(row["name"] as? String ?? "(unnamed institution)").fontWeight(.semibold)
                                Text("\(row["network"] as? String ?? "") · \(row["status"] as? String ?? "unknown") · \(row["city"] as? String ?? ""), \(row["country"] as? String ?? "")")
                                    .font(.caption).foregroundStyle(.secondary)
                                Text("Program wording: \((row["program_descriptions"] as? [String] ?? row["program_domains"] as? [String] ?? []).joined(separator: ", "))")
                                    .font(.caption).foregroundStyle(.secondary)
                                Text("Normalized domains: \((row["normalized_program_domains"] as? [String] ?? []).joined(separator: ", ")) · Audience wording: \((row["audience_descriptions"] as? [String] ?? row["audiences"] as? [String] ?? []).joined(separator: ", "))")
                                    .font(.caption).foregroundStyle(.secondary)
                                Text("Normalized audiences: \((row["normalized_audiences"] as? [String] ?? []).joined(separator: ", "))")
                                    .font(.caption).foregroundStyle(.secondary)
                                Text("Delivery modes: \((row["normalized_delivery_modes"] as? [String] ?? row["delivery_modes"] as? [String] ?? []).joined(separator: ", "))")
                                    .font(.caption).foregroundStyle(.secondary)
                                HStack {
                                    Button("Profile") { hub("registry-profile", ["entity_id": row["entity_id"] as? String ?? ""]) }
                                    Button("Set A") { compareLeftID = row["entity_id"] as? String ?? "" }
                                    Button("Set B") { compareRightID = row["entity_id"] as? String ?? "" }
                                    Button("Prepare monitor") {
                                        let labels = [row["name"] as? String ?? ""] + (row["aliases"] as? [String] ?? [])
                                        monitorName = "Monitor: \(row["name"] as? String ?? "institution")"
                                        monitorTerms = labels.filter { !$0.isEmpty }.joined(separator: "; ")
                                        monitorTargets = monitorTerms
                                    }
                                }.font(.caption)
                            }.padding(.vertical, 4)
                            Divider()
                        }
                        TextEditor(text: .constant(model.workspaceHubResults["registry-profile"].flatMap(Self.prettyJSON) ?? "Select an entity profile to inspect claims, conflicts, lifecycle, evidence, and relationships."))
                            .font(.system(.caption, design: .monospaced)).frame(minHeight: 145)
                        HStack {
                            TextField("Entity A ID", text: $compareLeftID)
                            TextField("Entity B ID", text: $compareRightID)
                            Toggle("Coverage documented", isOn: $comparisonCoverageDocumented).toggleStyle(.checkbox)
                            Button("Compare dimensions") {
                                guard !compareLeftID.isEmpty, !compareRightID.isEmpty else { return }
                                hub("registry-compare", ["left_entity_id": compareLeftID, "right_entity_id": compareRightID,
                                    "coverage_documented": comparisonCoverageDocumented])
                            }.buttonStyle(.borderedProminent)
                        }
                        TextEditor(text: .constant(model.workspaceHubResults["registry-compare"].flatMap(Self.prettyJSON) ?? "Comparison keeps geography, audiences, program/service, delivery, and institutional relationship separate. Popularity, effectiveness, outcomes, and causal influence are not assessed."))
                            .font(.system(.caption, design: .monospaced)).frame(minHeight: 150)
                    }
                }

                GroupBox("Preview and import a reference dataset") {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Picker("Blank schema", selection: $registryTemplate) {
                                Text("American Spaces").tag("american_spaces")
                                Text("EducationUSA").tag("educationusa")
                                Text("Language education centers").tag("language_education_centers")
                                Text("Technical training workshops").tag("technical_training_workshops")
                                Text("Custom network").tag("custom")
                            }
                            Button("Create template") { hub("registry-template", ["template": registryTemplate]) }
                        }
                        Text("Templates are blank schemas, not maintained or authoritative institution inventories.")
                            .font(.caption).foregroundStyle(.secondary)
                        HStack {
                            Text(registryFile.isEmpty ? "Drop a CSV, TSV, XLSX, XLS, JSON, or GeoJSON file" : registryFile).lineLimit(1)
                            Spacer()
                            Button("Choose…") { if let url = chooseFile(["csv", "tsv", "xlsx", "xls", "json", "geojson"]) { registryFile = url.path } }
                            Button("Preview") { guard !registryFile.isEmpty else { return }; hub("registry-preview", ["source_file": registryFile]) }
                        }
                        .onDrop(of: [UTType.fileURL], isTargeted: nil) { providers in receiveFiles(providers, forMap: false) }
                        HStack {
                            TextField("Dataset name", text: $registryDatasetName)
                            TextField("Network", text: $registryNetwork)
                            TextField("Geographic / temporal scope", text: $registryScope)
                        }
                        TextField("Known coverage limits", text: $registryLimits)
                        TextField("License and permitted-use notes", text: $registryLicense)
                        Toggle("Accept valid rows and record invalid-row exclusions", isOn: $registryAcceptPartial)
                        Text("Edit the suggested mapping from canonical fields to source column names:").font(.caption)
                        TextEditor(text: $registryMapping).font(.system(.caption, design: .monospaced)).frame(minHeight: 100)
                        TextEditor(text: .constant(model.workspaceHubResults["registry-preview"].flatMap(Self.prettyJSON) ?? "Preview counts, invalid rows, and sample records appear here before you confirm import."))
                            .font(.system(.caption, design: .monospaced)).frame(minHeight: 100)
                        TextEditor(text: .constant(model.workspaceHubResults["registry-import"].flatMap(Self.prettyJSON) ?? "Import results report additions, field changes, lifecycle claims, conflicts, invalid rows, and similar-name candidates. Similar names are suggested for analyst review and are never silently merged."))
                            .font(.system(.caption, design: .monospaced)).frame(minHeight: 115)
                        Button("Confirm import") { confirmRegistryImport() }.buttonStyle(.borderedProminent)
                    }
                }

                GroupBox("Add or connect entities") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Entity JSON supports names, aliases, location and precision, lifecycle dates, network, accounts, programs, audience, delivery mode, and host or partner institution names.")
                            .font(.caption).foregroundStyle(.secondary)
                        TextEditor(text: $registryEntityJSON).font(.system(.caption, design: .monospaced)).frame(minHeight: 125)
                        HStack {
                            TextField("Public evidence URL (required)", text: $registryEvidenceURL)
                            Picker("Claim review", selection: $registryReviewState) {
                                Text("Unreviewed").tag("unreviewed")
                                Text("Human verified").tag("human_verified")
                                Text("Needs follow-up").tag("needs_followup")
                            }.frame(width: 165)
                            Button("Save entity claim") { saveEntity() }.buttonStyle(.borderedProminent)
                        }
                        HStack {
                            TextField("Source entity ID", text: $relationshipSourceID)
                            TextField("Target entity ID", text: $relationshipTargetID)
                            TextField("Relationship type", text: $relationshipType)
                        }
                        HStack {
                            TextField("Relationship evidence URL", text: $relationshipEvidenceURL)
                            Button("Add relationship") { addRelationship() }
                        }
                    }
                }
            }.padding(12)
        }
    }

    private var mapTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                GroupBox("First-class, overlapping map layers") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("The canonical registry is the default reference layer. Add any number of CSV, XLSX, JSON, or GeoJSON datasets. Status markers retain closure evidence; dated views use documented lifecycle dates and do not reconstruct unknown former locations.")
                            .font(.caption).foregroundStyle(.secondary)
                        HStack {
                            TextField("Optional base activity/service data", text: $mapSourceFile)
                            Button("Choose…") { if let url = chooseFile(["csv", "xlsx"]) { mapSourceFile = url.path } }
                        }
                        Text("Reference layer files, one per line")
                        TextEditor(text: $mapLayers).font(.system(.caption, design: .monospaced)).frame(minHeight: 115)
                            .onDrop(of: [UTType.fileURL], isTargeted: nil) { providers in receiveFiles(providers, forMap: true) }
                        HStack {
                            TextField("Optional as-of date YYYY-MM-DD", text: $mapAsOfDate)
                            Button("Build map") { buildMap() }.buttonStyle(.borderedProminent)
                        }
                        Text(model.outputs.last ?? "Map output will appear in Activity after generation.")
                            .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                }
            }.padding(12)
        }
    }

    private var dataTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                GroupBox("Inspect and export underlying data") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Browse source records, observations, assessments, project exports, or reference files. Filter one field and export the matching rows without reducing them to a map or summary.")
                            .font(.caption).foregroundStyle(.secondary)
                        HStack {
                            TextField("CSV / XLSX / JSONL / GeoJSON file", text: $dataFile)
                            Button("Choose…") { if let url = chooseFile(["csv", "tsv", "xlsx", "xls", "json", "geojson", "jsonl", "ndjson"]) { dataFile = url.path } }
                        }
                        .onDrop(of: [UTType.fileURL], isTargeted: nil) { providers in receiveDataFiles(providers) }
                        HStack {
                            TextField("Filter column", text: $dataFilterColumn)
                            TextField("Contains", text: $dataFilterValue)
                            Button("Browse / filter") {
                                guard !dataFile.isEmpty else { return }
                                hub("dataset-browse", ["source_file": dataFile, "filter_column": dataFilterColumn,
                                    "filter_value": dataFilterValue, "max_rows": 1000])
                            }.buttonStyle(.borderedProminent)
                            Button("Export filtered rows") {
                                guard !dataFile.isEmpty else { return }
                                guard let target = saveFile("csv") else { return }
                                hub("dataset-export", ["source_file": dataFile, "filter_column": dataFilterColumn,
                                    "filter_value": dataFilterValue, "output_file": target.path])
                            }
                        }
                        if let result = model.workspaceHubResults["dataset-browse"] as? [String: Any] {
                            Text("\(result["matching_rows"] as? Int ?? 0) matching / \(result["row_count"] as? Int ?? 0) source rows · displaying \(result["rows_shown"] as? Int ?? 0) · fields: \((result["columns"] as? [String] ?? []).joined(separator: ", "))")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        ForEach(Array(dataRows.enumerated()), id: \.offset) { entry in
                            let row = entry.element
                            DisclosureGroup("\(row["published_at"] as? String ?? row["date_iso"] as? String ?? "") · \(row["platform"] as? String ?? "") · \(row["author_handle"] as? String ?? row["name"] as? String ?? row["record_key"] as? String ?? "record")") {
                                Text(Self.prettyJSON(row) ?? "")
                                    .font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                            }
                            Divider()
                        }
                        if let output = model.outputs.last, model.workspaceHubAction == "dataset-export" {
                            Text("Exported: \(output)").font(.caption).textSelection(.enabled)
                        }
                    }
                }
            }.padding(12)
        }
    }

    private var monitoringTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                GroupBox("Saved listening posts") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Cadence marks when a monitor becomes due. Run due monitors here or schedule `sugar-project monitor-run-due <project-folder>` with Task Scheduler or launchd. Each run keeps raw source output and adds deduplicated new or changed records to the project review feed.")
                            .font(.caption).foregroundStyle(.secondary)
                        TextField("Name", text: $monitorName)
                        TextField("Search terms (semicolon separated)", text: $monitorTerms)
                        TextField("Organizations or public handles to monitor", text: $monitorTargets)
                        TextField("Sources: bilibili; weibo; x; bluesky; mastodon", text: $monitorSources)
                        HStack {
                            TextField("Geographies for analyst context", text: $monitorGeographies)
                            Stepper("Cadence: \(Int(monitorCadence)) min", value: $monitorCadence, in: 5...525600, step: 60)
                        }
                        HStack {
                            Button("Save listening post") { saveMonitor() }.buttonStyle(.borderedProminent)
                            Button("Refresh monitors") { hub("monitor-list") }
                            Button("Run selected") { guard !selectedMonitorID.isEmpty else { return }; hub("monitor-run", ["monitor_id": selectedMonitorID]) }
                            Button("Run due now") { hub("monitor-run-due", ["max_monitors": 25]) }
                            Button("Pause / resume") { toggleMonitor() }
                            Button("Load evidence feed") { loadMonitorFeed() }
                        }
                        Toggle("Automatically run due posts while SUGAR is open", isOn: $automaticMonitoring)
                            .toggleStyle(.checkbox)
                        ForEach(Array(monitorRows.enumerated()), id: \.offset) { entry in
                            let row = entry.element
                            Button {
                                selectedMonitorID = row["monitor_id"] as? String ?? ""
                                hub("monitor-feed", ["monitor_id": selectedMonitorID])
                            } label: {
                                VStack(alignment: .leading) {
                                    Text(row["name"] as? String ?? "Listening post").fontWeight(.semibold)
                                    Text("\(row["status"] as? String ?? "") · every \(row["cadence_minutes"] as? Int ?? 0) min · next due \(row["next_due_at"] as? String ?? "") · last run \(row["last_run_status"] as? String ?? "not run")")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }.buttonStyle(.plain)
                            Divider()
                        }
                        if let result = model.workspaceHubResults["monitor-run-due"], let text = Self.prettyJSON(result) {
                            TextEditor(text: .constant(text)).font(.system(.caption, design: .monospaced)).frame(minHeight: 105)
                        }
                    }
                }

                GroupBox("Incoming evidence review") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Selected listening post: \(selectedMonitorID.isEmpty ? "all posts" : selectedMonitorID)")
                            .font(.caption).foregroundStyle(.secondary)
                        ForEach(Array(materialRows.enumerated()), id: \.offset) { entry in
                            let row = entry.element
                            Button {
                                selectedMaterialID = row["material_id"] as? String ?? ""
                            } label: {
                                VStack(alignment: .leading) {
                                    Text("\(row["change_state"] as? String ?? "new") · \(row["actor_handle"] as? String ?? "unknown actor") · \(row["platform"] as? String ?? "")")
                                    Text("\(row["monitor_name"] as? String ?? "") · \(row["published_at"] as? String ?? "") · \(row["review_state"] as? String ?? "unreviewed")")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }.buttonStyle(.plain)
                        }
                        TextField("Analyst note", text: $reviewNote)
                        HStack {
                            Button("Verify") { reviewMaterial("human_verified") }
                            Button("Needs follow-up") { reviewMaterial("needs_followup") }
                            Button("Reject") { reviewMaterial("rejected") }
                        }
                    }
                }
            }.padding(12)
        }
    }

    private var conversationHelpTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                GroupBox("Handle and conversation view") {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            TextField("Source record CSV, XLSX, JSONL, or NDJSON", text: $conversationFile)
                            Button("Choose…") { if let url = chooseFile(["csv", "xlsx", "jsonl", "ndjson"]) { conversationFile = url.path } }
                        }
                        HStack {
                            TextField("Optional conversation/thread ID", text: $conversationID)
                            Button("Build view") {
                                guard !conversationFile.isEmpty else { return }
                                hub("conversation-view", ["source_file": conversationFile, "conversation_id": conversationID])
                            }
                        }
                        TextEditor(text: .constant(model.workspaceHubResults["conversation-view"].flatMap(Self.prettyJSON) ?? "Conversation view displays handle identity and source-provided reply, quote, mention, and thread relationships."))
                            .font(.system(.caption, design: .monospaced)).frame(minHeight: 230)
                    }
                }
                GroupBox("Workflow and evidence rules") {
                    Text("1. Create a project, then make subprojects for research tracks.\n\n2. Preview reference data, verify its field map, record network/geography/date scope and permitted use, then import. Every claim retains source evidence; contradictions remain visible.\n\n3. Compare geography, audience, program domain, delivery mode, institutional relationships, and time as separate dimensions. Distance is not competition, popularity, or effectiveness.\n\n4. Save listening posts, run them when due, and review the incoming evidence feed. The one-shot due-run command can be scheduled by the operating system.\n\n5. Export a portable bundle for analyst handoff. Credentials are never included and each analyst supplies their own authorized access. SUGAR documents observable activity and public signals; it does not infer outcomes or causal influence.")
                        .font(.callout).textSelection(.enabled)
                }
                GroupBox("Troubleshooting") {
                    Text("A registry preview with no usable rows usually means the source column mapping needs correction; review the sample and row errors before importing. A missing map marker means coordinates are absent, invalid, or intentionally too imprecise to plot. A zero-result monitor run is different from a failed or unavailable source; inspect run coverage in project history. Due monitors run only when you opt in to desktop polling or schedule the CLI command. A project bundle imports into a new or empty destination. A missing conversation parent means the source record was not collected; SUGAR does not reconstruct it.")
                        .font(.callout).textSelection(.enabled)
                }
            }.padding(12)
        }
    }

    private func createOrOpenProject() {
        guard !model.activeWorkspace.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            let alert = NSAlert()
            alert.messageText = "Choose a project folder"
            alert.informativeText = "Select the folder for this project before creating or opening it."
            alert.addButton(withTitle: "OK")
            alert.runModal()
            return
        }
        let manifest = URL(fileURLWithPath: model.activeWorkspace).appendingPathComponent("sugar-project.json").path
        if FileManager.default.fileExists(atPath: manifest) {
            hub("dashboard")
        } else {
            model.run(command: "workspace-init", config: ["workspace": model.activeWorkspace, "name": projectName, "exist_ok": false])
        }
    }

    private func hub(_ action: String, _ values: [String: Any] = [:]) {
        var config = values
        config["action"] = action
        config["actor"] = analystName.isEmpty ? "analyst" : analystName
        if action != "project-list" && action != "project-import" { config["workspace"] = model.activeWorkspace }
        model.run(command: "workspace-hub", config: config)
    }

    private func loadRegistry() {
        var filters: [String: Any] = [:]
        if !registryQuery.isEmpty { filters["query"] = registryQuery }
        if !registryNetwork.isEmpty { filters["network"] = registryNetwork }
        if !registryStatus.isEmpty { filters["status"] = registryStatus }
        hub("registry-list", ["filters": filters])
    }

    private func confirmRegistryImport() {
        guard !registryFile.isEmpty,
              let mappingData = registryMapping.data(using: .utf8),
              let mapping = try? JSONSerialization.jsonObject(with: mappingData) as? [String: String],
              !mapping["name", default: ""].isEmpty else { return }
        let alert = NSAlert()
        alert.messageText = "Import this reference dataset?"
        let invalidCount = (model.workspaceHubResults["registry-preview"] as? [String: Any])?["error_count"] as? Int ?? 0
        if invalidCount > 0 && !registryAcceptPartial {
            let warning = NSAlert()
            warning.messageText = "Review invalid rows before import"
            warning.informativeText = "Preview found \(invalidCount) invalid rows. Correct the mapping/source or enable the explicit option to import valid rows and record the exclusions."
            warning.addButton(withTitle: "OK")
            warning.runModal()
            return
        }
        alert.informativeText = "SUGAR will retain the original dataset, its declared scope and license notes, and row-level source references. \(invalidCount > 0 ? "The \(invalidCount) invalid rows will be excluded and reported." : "")"
        alert.addButton(withTitle: "Import")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        hub("registry-import", ["source_file": registryFile, "mapping": mapping,
            "dataset_name": registryDatasetName, "network": registryNetwork, "geographic_scope": registryScope,
            "known_coverage_limits": registryLimits, "license_notes": registryLicense,
            "accept_partial": registryAcceptPartial])
    }

    private func saveEntity() {
        guard let data = registryEntityJSON.data(using: .utf8),
              let entity = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              !registryEvidenceURL.isEmpty else { return }
        hub("registry-upsert", ["entity": entity, "evidence_refs": [["source_url": registryEvidenceURL]], "review_state": registryReviewState])
    }

    private func addRelationship() {
        guard !relationshipSourceID.isEmpty, !relationshipTargetID.isEmpty, !relationshipEvidenceURL.isEmpty else { return }
        hub("registry-relationship", ["source_entity_id": relationshipSourceID, "target_entity_id": relationshipTargetID,
            "relationship_type": relationshipType, "evidence_refs": [["source_url": relationshipEvidenceURL]]])
    }

    private func buildMap() {
        let layerFiles = mapLayers.split(whereSeparator: \.isNewline).map(String.init).filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        let output = URL(fileURLWithPath: model.activeWorkspace).appendingPathComponent("maps/research_workspace_map.html").path
        hub("registry-map", ["source_file": mapSourceFile, "reference_files": layerFiles,
            "as_of_date": mapAsOfDate, "output_file": output])
    }

    private func saveMonitor() {
        func values(_ text: String) -> [String] { text.split(separator: ";").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }
        hub("monitor-save", ["name": monitorName, "terms": values(monitorTerms), "target_entities": values(monitorTargets),
            "sources": values(monitorSources), "geographies": values(monitorGeographies), "cadence_minutes": Int(monitorCadence)])
    }

    private func toggleMonitor() {
        guard let monitor = monitorRows.first(where: { ($0["monitor_id"] as? String) == selectedMonitorID }) else { return }
        hub("monitor-status", ["monitor_id": selectedMonitorID, "status": (monitor["status"] as? String) == "active" ? "paused" : "active"])
    }

    private func loadMonitorFeed() {
        hub("monitor-feed", ["monitor_id": selectedMonitorID])
    }

    private func reviewMaterial(_ state: String) {
        guard !selectedMaterialID.isEmpty else { return }
        hub("monitor-review", ["material_id": selectedMaterialID, "review_state": state, "note": reviewNote])
    }

    private func rerunLatestSearch() {
        guard let history = model.workspaceHubResults["project-history"] as? [[String: Any]],
              let run = history.first(where: { row in
                  guard row["event_type"] as? String == "research_run", let details = row["details"] as? [String: Any] else { return false }
                  return ["search", "research-collect"].contains(details["command"] as? String ?? "")
              }), let details = run["details"] as? [String: Any],
              let command = details["command"] as? String,
              var config = details["parameters"] as? [String: Any] else { return }
        config["workspace"] = model.activeWorkspace
        config.removeValue(forKey: "source_coverage")
        config.removeValue(forKey: "effective_sources")
        config.removeValue(forKey: "effective_terms")
        config["output_directory"] = URL(fileURLWithPath: model.activeWorkspace)
            .appendingPathComponent("raw/reruns/\(UUID().uuidString)").path
        model.run(command: command, config: config)
    }

    private func receiveFiles(_ providers: [NSItemProvider], forMap: Bool) -> Bool {
        guard let provider = providers.first else { return false }
        provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
            let url: URL?
            if let value = item as? URL { url = value }
            else if let data = item as? Data { url = URL(dataRepresentation: data, relativeTo: nil) }
            else { url = nil }
            guard let url else { return }
            DispatchQueue.main.async {
                if forMap {
                    mapLayers += (mapLayers.isEmpty ? "" : "\n") + url.path
                } else {
                    registryFile = url.path
                    registryDatasetName = url.deletingPathExtension().lastPathComponent
                    hub("registry-preview", ["source_file": url.path])
                }
            }
        }
        return true
    }

    private func receiveDataFiles(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }
        provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
            let url: URL?
            if let value = item as? URL { url = value }
            else if let data = item as? Data { url = URL(dataRepresentation: data, relativeTo: nil) }
            else { url = nil }
            guard let url else { return }
            DispatchQueue.main.async {
                dataFile = url.path
                hub("dataset-browse", ["source_file": url.path, "max_rows": 1000])
            }
        }
        return true
    }

    private static func prettyJSON(_ value: Any) -> String? {
        guard JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

struct ResearchProjectView: View {
    @EnvironmentObject var model: AppModel

    @Binding var workspace: String
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
    @State private var hypothesesFile = ""
    @State private var entityAliasesFile = ""
    @State private var captureHTMLFile = ""
    @State private var captureSourceURL = ""
    @State private var mediaFile = ""
    @State private var mediaSourceURL = ""
    @State private var mediaTranscriptFile = ""
    @State private var mediaOCRFile = ""
    @State private var mediaLanguage = ""
    @State private var mediaParentRecordID = ""
    @State private var mediaManifestFile = ""
    @State private var mediaObservationID = ""
    @State private var mediaStart = ""
    @State private var mediaEnd = ""
    @State private var mediaQuote = ""
    @State private var nextEvidenceQueryBudget = 10
    @State private var nextEvidenceRecordBudget = 300
    @State private var semanticQuery = ""
    @State private var semanticTopK = 20
    @State private var useRemoteEmbeddings = false

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

            Section("3b. Research intelligence feedback") {
                Text("Use measured plan yield, open requirement scope, and optional competing hypotheses to choose the next bounded collection. These checks run locally and never start collection automatically.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                HStack {
                    Stepper("Query actions: \(nextEvidenceQueryBudget)", value: $nextEvidenceQueryBudget, in: 1...100)
                    Stepper("Max records per query: \(nextEvidenceRecordBudget)", value: $nextEvidenceRecordBudget, in: 1...10000, step: 50)
                }
                HStack {
                    TextField("Optional hypothesis / synthesis JSON", text: $hypothesesFile)
                    Button("Choose...") {
                        if let url = chooseFile(["json"]) { hypothesesFile = url.path }
                    }
                }
                HStack {
                    TextField("Optional canonical entity alias registry JSON", text: $entityAliasesFile)
                    Button("Choose...") {
                        if let url = chooseFile(["json"]) { entityAliasesFile = url.path }
                    }
                }
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Button("Recommend Next Collection") {
                            var config: [String: Any] = [
                                "workspace": cleanWorkspace,
                                "max_queries": nextEvidenceQueryBudget,
                                "max_records_per_query": nextEvidenceRecordBudget,
                            ]
                            if !hypothesesFile.isEmpty { config["hypotheses"] = hypothesesFile }
                            model.run(command: "intel-next-evidence", config: config)
                        }
                        .buttonStyle(.borderedProminent)
                        Button("Analyze Source Text Lineage") {
                            model.run(command: "intel-content-lineage", config: ["workspace": cleanWorkspace])
                        }
                    }
                    HStack {
                        Button("Build Temporal Evidence Graph") {
                            var config: [String: Any] = ["workspace": cleanWorkspace]
                            if !entityAliasesFile.isEmpty { config["entity_aliases"] = entityAliasesFile }
                            model.run(command: "intel-evidence-graph", config: config)
                        }
                        Button("Test Finding Robustness") {
                            model.run(command: "intel-robustness", config: ["workspace": cleanWorkspace])
                        }
                    }
                }
                .disabled(model.isRunning || cleanWorkspace.isEmpty)
                Text("Lineage shows text-similarity candidates, not proof of copying. Graph edges link entities to evidence-bearing observations; they do not infer direct ties. Robustness reports leave-one-source-out changes on human-verified, brief-eligible evidence.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("3c. Search the evidence corpus") {
                TextField("Question or phrase", text: $semanticQuery)
                Stepper("Maximum results: \(semanticTopK)", value: $semanticTopK, in: 1...500)
                Toggle("Use remote multilingual embeddings. This sends the query and changed corpus text to the configured provider.", isOn: $useRemoteEmbeddings)
                HStack {
                    Spacer()
                    Button("Search Evidence") {
                        var config: [String: Any] = [
                            "workspace": cleanWorkspace,
                            "query": semanticQuery,
                            "top_k": semanticTopK,
                            "remote_embeddings": useRemoteEmbeddings,
                        ]
                        if useRemoteEmbeddings {
                            config["llm"] = llmSelection.provider.configuration(
                                model: "text-embedding-3-small",
                                customBaseURL: baseURL
                            )
                        }
                        model.run(command: "intel-semantic-search", config: config)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.isRunning || cleanWorkspace.isEmpty || semanticQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                Text("Local search stays on this computer. Embedding vectors only rank candidate retrieval and are not evidence; open the original sources before citing them.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("3d. Analyst capture and multimodal evidence") {
                Text("Save a page through ordinary public or authorized access, then import its HTML snapshot. SUGAR removes scripts, hidden controls, and credential-like fields. Media is preserved locally; supplied transcripts and OCR remain unreviewed.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                HStack {
                    TextField("Saved .html page", text: $captureHTMLFile)
                    Button("Choose...") {
                        if let url = chooseFile(["html", "htm"]) { captureHTMLFile = url.path }
                    }
                }
                TextField("Original public or authorized URL", text: $captureSourceURL)
                HStack {
                    Spacer()
                    Button("Save Sanitized Page to Project") {
                        model.run(command: "intel-capture-page", config: [
                            "workspace": cleanWorkspace,
                            "html_file": captureHTMLFile,
                            "source_url": captureSourceURL,
                        ])
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.isRunning || cleanWorkspace.isEmpty || captureHTMLFile.isEmpty || captureSourceURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                HStack {
                    TextField("Image / audio / video file", text: $mediaFile)
                    Button("Choose...") {
                        if let url = chooseFile(["png", "jpg", "jpeg", "webp", "mp4", "mov", "m4v", "mp3", "wav", "m4a"]) { mediaFile = url.path }
                    }
                }
                TextField("Media source URL (optional)", text: $mediaSourceURL)
                HStack {
                    TextField("Transcript / subtitle file (optional)", text: $mediaTranscriptFile)
                    Button("Choose...") {
                        if let url = chooseFile(["vtt", "srt", "txt"]) { mediaTranscriptFile = url.path }
                    }
                }
                HStack {
                    TextField("OCR text file (optional)", text: $mediaOCRFile)
                    Button("Choose...") {
                        if let url = chooseFile(["txt"]) { mediaOCRFile = url.path }
                    }
                }
                HStack {
                    TextField("Language", text: $mediaLanguage)
                    TextField("Parent record ID", text: $mediaParentRecordID)
                }
                HStack {
                    Spacer()
                    Button("Preserve Media and Derivatives") {
                        var config: [String: Any] = [
                            "workspace": cleanWorkspace,
                            "media_file": mediaFile,
                            "source_url": mediaSourceURL,
                            "language": mediaLanguage,
                            "parent_record_id": mediaParentRecordID,
                        ]
                        if !mediaTranscriptFile.isEmpty { config["transcript"] = mediaTranscriptFile }
                        if !mediaOCRFile.isEmpty { config["ocr"] = mediaOCRFile }
                        model.run(command: "intel-media-ingest", config: config)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.isRunning || cleanWorkspace.isEmpty || mediaFile.isEmpty)
                }
                HStack {
                    TextField("Preserved media manifest JSON", text: $mediaManifestFile)
                    Button("Choose...") {
                        if let url = chooseFile(["json"]) { mediaManifestFile = url.path }
                    }
                }
                TextField("Observation ID", text: $mediaObservationID)
                HStack {
                    TextField("Start time", text: $mediaStart)
                    TextField("End time", text: $mediaEnd)
                }
                TextField("Quote / description", text: $mediaQuote)
                HStack {
                    Spacer()
                    Button("Attach Timestamped Citation to New Observations File") {
                        model.run(command: "intel-media-attach", config: [
                            "workspace": cleanWorkspace,
                            "media_manifest": mediaManifestFile,
                            "observation_id": mediaObservationID,
                            "media_start": mediaStart,
                            "media_end": mediaEnd,
                            "quote": mediaQuote,
                        ])
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.isRunning || cleanWorkspace.isEmpty || mediaManifestFile.isEmpty || mediaObservationID.isEmpty || mediaStart.isEmpty || mediaEnd.isEmpty)
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
