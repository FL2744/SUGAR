import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";
import { configureApi, createWorkspace, defaultApiUrl, downloadWorkspaceFile, hubData, latestEvent, listWorkspaces, runBackend, uploadWorkspaceFile, type ApiWorkspace, type Credentials } from "./bridge";
import { InstitutionMap, institutionCoordinates } from "./map-view";
import type { BackendEvent, Institution, SecretKey } from "./types";

type Page = "home" | "project" | "institutions" | "activity" | "settings";
type ActivityItem = { id: number; time: string; title: string; detail: string; kind: "ok" | "error" | "info" };
type Dashboard = {
  name?: string;
  description?: string;
  artifact_count?: number;
  missing_artifacts?: number;
  pending_review?: number;
  collection_issues?: number;
  artifacts?: Array<{ kind?: string; path?: string; external?: boolean; exists?: boolean }>;
  research_requirement?: { question?: string; geographies?: string[]; known_entities?: string[]; target_audiences?: string[] };
  search_plan?: Record<string, unknown>;
};
type RegistryData = { entities?: Institution[]; count?: number; relationships?: number };
type RegistryPreview = { columns?: string[]; suggested_mapping?: Record<string, string>; sample_rows?: Record<string, unknown>[]; row_count?: number; [key: string]: unknown };
type EvidencePreview = { columns?: string[]; rows?: Record<string, unknown>[]; row_count?: number; matching_rows?: number };

const NAV: Array<{ id: Page; label: string; icon: string }> = [
  { id: "home", label: "Overview", icon: "◫" },
  { id: "project", label: "Research project", icon: "⌕" },
  { id: "institutions", label: "Institutions & map", icon: "⌖" },
  { id: "activity", label: "Run history", icon: "↗" },
];
const SECRET_FIELDS: Array<{ key: SecretKey; label: string; placeholder: string }> = [
  { key: "llm_api_key", label: "LLM provider key", placeholder: "Optional · for assisted workflows" },
  { key: "x_bearer_token", label: "X bearer token", placeholder: "Optional" },
  { key: "bluesky_identifier", label: "Bluesky identifier", placeholder: "Optional" },
  { key: "bluesky_app_password", label: "Bluesky app password", placeholder: "Optional" },
  { key: "mastodon_token", label: "Mastodon access token", placeholder: "Optional" },
  { key: "weibo_cookie", label: "Weibo cookie", placeholder: "Optional" },
];

function titleCase(value: string) {
  return value.replaceAll("_", " ").replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function summarizeEvent(event: BackendEvent): { title: string; detail: string } {
  if (event.event === "workspace_hub_data") {
    const data = event.data as Record<string, unknown> | undefined;
    const count = Array.isArray(data?.entities) ? `${data.entities.length} institutions` : "Research workspace data refreshed";
    return { title: titleCase(String(event.action || "workspace")), detail: count };
  }
  if (event.event === "complete") {
    const outputs = Array.isArray(event.outputs) ? event.outputs : [];
    return { title: "Operation complete", detail: outputs.length ? `${outputs.length} output${outputs.length === 1 ? "" : "s"} saved` : "Workspace updated" };
  }
  if (event.event === "workspace_status") {
    const name = String(event.name || "Research project");
    return { title: "Project opened", detail: name };
  }
  if (event.event === "backend") return { title: "Research engine ready", detail: `SUGAR ${String(event.version || "")} · Python bridge connected` };
  if (event.event === "error") return { title: "Research engine reported an error", detail: String(event.message || "Unknown backend error") };
  if (event.event === "backend-stderr") return { title: "Engine diagnostic", detail: String(event.message || "") };
  return { title: titleCase(String(event.event || "Research update")), detail: String(event.message || event.operation || "") };
}

function extractEvidence(row: Institution): Array<{ label: string; url: string }> {
  const found = new Map<string, string>();
  const add = (label: unknown, url: unknown) => {
    if (typeof url === "string" && /^https?:\/\//i.test(url)) found.set(url, String(label || new URL(url).hostname));
  };
  for (const item of row.evidence_refs || []) add(item.title || item.citation, item.source_url);
  for (const item of row.source_evidence || []) add(item.title, item.source_url);
  for (const claim of row.claims || []) {
    const refs = claim.evidence_refs;
    if (Array.isArray(refs)) for (const ref of refs) {
      if (ref && typeof ref === "object") add((ref as Record<string, unknown>).title, (ref as Record<string, unknown>).source_url);
    }
  }
  for (const url of row.public_links || []) add("Institution website", url);
  return [...found.entries()].map(([url, label]) => ({ label, url }));
}

export function App() {
  const [page, setPage] = useState<Page>("home");
  const [workspace, setWorkspace] = useState(() => localStorage.getItem("sugar.workspace") || "");
  const [projectName, setProjectName] = useState("State Research Project");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [registry, setRegistry] = useState<Institution[]>([]);
  const [registryRelationships, setRegistryRelationships] = useState(0);
  const [selected, setSelected] = useState<Institution | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [engineState, setEngineState] = useState<"checking" | "ready" | "unavailable" | "preview">("checking");
  const [engineVersion, setEngineVersion] = useState("");
  const [apiUrl, setApiUrl] = useState(() => defaultApiUrl());
  const [apiToken, setApiToken] = useState("");
  const [workspacePickerOpen, setWorkspacePickerOpen] = useState(false);
  const [remoteWorkspaces, setRemoteWorkspaces] = useState<ApiWorkspace[]>([]);
  const [remoteProjectName, setRemoteProjectName] = useState("State Research Project");
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [credentials, setCredentials] = useState<Credentials>({});
  const [question, setQuestion] = useState("");
  const [geography, setGeography] = useState("");
  const [knownEntities, setKnownEntities] = useState("");
  const [audience, setAudience] = useState("Policy researchers");
  const [requirementSaved, setRequirementSaved] = useState(false);
  const [plan, setPlan] = useState<Record<string, unknown> | null>(null);
  const [evidenceFile, setEvidenceFile] = useState("");
  const [evidenceRecordsPath, setEvidenceRecordsPath] = useState("");
  const [evidencePreview, setEvidencePreview] = useState<EvidencePreview | null>(null);
  const [reviewPrepared, setReviewPrepared] = useState(false);
  const [query, setQuery] = useState("");
  const [network, setNetwork] = useState("All networks");
  const [statusFilter, setStatusFilter] = useState("All statuses");
  const [datasetFile, setDatasetFile] = useState("");
  const [datasetName, setDatasetName] = useState("");
  const [datasetFileLabel, setDatasetFileLabel] = useState("");
  const [datasetNetwork, setDatasetNetwork] = useState("");
  const [mappingText, setMappingText] = useState("{}");
  const [preview, setPreview] = useState<RegistryPreview | null>(null);
  const evidenceInputRef = useRef<HTMLInputElement>(null);
  const datasetInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => configureApi(apiUrl, apiToken), [apiUrl, apiToken]);

  const addActivity = useCallback((title: string, detail: string, kind: ActivityItem["kind"] = "ok") => {
    setActivity((items) => [{ id: Date.now() + Math.random(), time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), title, detail, kind }, ...items].slice(0, 100));
  }, []);

  const execute = useCallback(async (operation: string, config?: Record<string, unknown>) => {
    if (busy) return null;
    setBusy(operation);
    setError("");
    try {
      const result = await runBackend(operation, config, credentials);
      const quietHubAction = operation === "workspace-hub" && ["dashboard", "project-history", "registry-list"].includes(String(config?.action || ""));
      if (!quietHubAction) {
        for (const event of result.events) {
          const item = summarizeEvent(event);
          if (item.title !== "Research engine ready" && item.title !== "Operation complete") addActivity(item.title, item.detail, event.event === "error" ? "error" : "info");
        }
      }
      return result;
    } catch (issue) {
      const message = issue instanceof Error ? issue.message : String(issue);
      setError(message);
      addActivity(titleCase(operation), message, "error");
      return null;
    } finally {
      setBusy("");
    }
  }, [busy, credentials, addActivity]);

  const refreshDashboard = useCallback(async (path = workspace) => {
    if (!path) return;
    const result = await execute("workspace-hub", { action: "dashboard", workspace: path });
    if (!result) return;
    const data = hubData<Dashboard>(result.events, "dashboard");
    if (data) {
      setDashboard(data);
      if (data.name) setProjectName(data.name);
      const imported = [...(data.artifacts || [])].reverse().find((item) => item.kind === "import" && item.path?.toLowerCase().endsWith(".jsonl"));
      setEvidenceRecordsPath(imported ? imported.external ? imported.path || "" : `${path}/${imported.path || ""}` : "");
      setReviewPrepared(Boolean(data.artifacts?.some((item) => item.kind === "observations")));
      const requirement = data.research_requirement;
      if (requirement) {
        setQuestion(String(requirement.question || ""));
        setGeography(Array.isArray(requirement.geographies) ? requirement.geographies.join(", ") : "");
        setKnownEntities(Array.isArray(requirement.known_entities) ? requirement.known_entities.join(", ") : "");
        setAudience(Array.isArray(requirement.target_audiences) ? requirement.target_audiences.join(", ") : "");
      }
      setRequirementSaved(Boolean(requirement || data.artifacts?.some((item) => item.kind === "research_requirement")));
      setPlan(data.search_plan && typeof data.search_plan === "object" ? data.search_plan : null);
    }
    const history = await execute("workspace-hub", { action: "project-history", workspace: path, limit: 100 });
    if (history) {
      const rows = hubData<unknown[]>(history.events, "project-history");
      if (Array.isArray(rows)) {
        setActivity(rows.slice(0, 40).map((row, index) => {
          const value = row as Record<string, unknown>;
          const details = (value.details && typeof value.details === "object" ? value.details : {}) as Record<string, unknown>;
          const status = String(value.status || details.status || "");
          return { id: index + 1, time: String(value.occurred_at || value.started_at || value.created_at || ""), title: titleCase(String(value.command || details.operation || value.event_type || "Project event")), detail: status || String(value.summary || details.message || "Recorded in project history"), kind: status === "failed" ? "error" : "ok" };
        }));
      }
    }
    const registryResult = await execute("workspace-hub", { action: "registry-list", workspace: path });
    const registryData = registryResult && hubData<RegistryData>(registryResult.events, "registry-list");
    if (registryData) {
      setRegistry(registryData.entities || []);
      setRegistryRelationships(registryData.relationships || 0);
    }
  }, [workspace, execute]);

  useEffect(() => {
    if (!workspace) return;
    void refreshDashboard(workspace);
  }, [workspace]);

  useEffect(() => {
    let active = true;
    setEngineState("checking");
    void runBackend("diagnostics", undefined, credentials).then((result) => {
      if (!active) return;
      const diagnostics = latestEvent<Record<string, unknown>>(result.events, "diagnostics");
      setEngineVersion(String(diagnostics?.version || ""));
      setEngineState("ready");
    }).catch((issue: unknown) => {
      if (!active) return;
      setEngineState("unavailable");
      setError(issue instanceof Error ? issue.message : String(issue));
    });
    return () => { active = false; };
  }, [apiUrl]);

  const filteredRows = useMemo(() => registry.filter((row) => {
    const haystack = [row.name, row.network, row.entity_type, row.city, row.country, row.description].join(" ").toLowerCase();
    const matchesNetwork = network === "All networks" || row.network === network;
    const matchesStatus = statusFilter === "All statuses" || (row.status || "unknown").toLowerCase() === statusFilter.toLowerCase();
    return (!query || haystack.includes(query.toLowerCase())) && matchesNetwork && matchesStatus;
  }), [registry, network, statusFilter, query]);
  const networks = useMemo(() => ["All networks", ...new Set(registry.map((row) => row.network).filter((item): item is string => Boolean(item)))], [registry]);
  const locatedCount = useMemo(() => registry.filter((row) => institutionCoordinates(row) !== null).length, [registry]);

  const chooseWorkspace = async () => {
    if (!isTauri()) {
      setBusy("loading-projects");
      setError("");
      try {
        setRemoteWorkspaces(await listWorkspaces());
        setRemoteProjectName(projectName || "Research project");
        setWorkspacePickerOpen(true);
      } catch (issue) {
        setError(issue instanceof Error ? issue.message : String(issue));
      } finally { setBusy(""); }
      return;
    }
    const selectedPath = await open({ directory: true, multiple: false, title: "Select a SUGAR project folder" });
    if (typeof selectedPath !== "string") return;
    setBusy("workspace-status");
    try {
      let result = await runBackend("workspace-status", { workspace: selectedPath }, credentials);
      let status = latestEvent<Record<string, unknown>>(result.events, "workspace_status");
      if (!status) {
        result = await runBackend("workspace-init", { workspace: selectedPath, name: projectName.trim() || "Research project", exist_ok: true }, credentials);
        status = latestEvent<Record<string, unknown>>(result.events, "workspace_status");
      }
      setWorkspace(selectedPath);
      localStorage.setItem("sugar.workspace", selectedPath);
      if (status?.name) setProjectName(String(status.name));
      addActivity("Project opened", String(status?.name || selectedPath), "ok");
      setPage("home");
    } catch (issue) {
      const message = issue instanceof Error ? issue.message : String(issue);
      if (message.includes("No such file") || message.includes("does not exist") || message.includes("FileNotFoundError")) {
        const created = await runBackend("workspace-init", { workspace: selectedPath, name: projectName.trim() || "Research project", exist_ok: true }, credentials).catch(() => null);
        if (created) {
          setWorkspace(selectedPath);
          localStorage.setItem("sugar.workspace", selectedPath);
          addActivity("Project created", projectName, "ok");
          setPage("home");
        } else setError(message);
      } else setError(message);
    } finally { setBusy(""); }
  };

  const openRemoteWorkspace = (item: ApiWorkspace) => {
    setWorkspace(item.workspace);
    setProjectName(item.name);
    localStorage.setItem("sugar.workspace", item.workspace);
    setWorkspacePickerOpen(false);
    addActivity("Project opened", item.name, "ok");
    setPage("home");
  };

  const createRemoteWorkspace = async (event: FormEvent) => {
    event.preventDefault();
    if (!remoteProjectName.trim()) return;
    setBusy("creating-project");
    setError("");
    try {
      const created = await createWorkspace(remoteProjectName.trim());
      setRemoteWorkspaces((items) => [created, ...items]);
      openRemoteWorkspace(created);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : String(issue));
    } finally { setBusy(""); }
  };

  const connectResearchEngine = async () => {
    configureApi(apiUrl, apiToken);
    setBusy("connecting-api");
    setError("");
    try {
      const result = await runBackend("diagnostics", undefined, credentials);
      const diagnostics = latestEvent<Record<string, unknown>>(result.events, "diagnostics");
      setEngineVersion(String(diagnostics?.version || ""));
      setEngineState("ready");
      addActivity("Research API connected", `SUGAR ${String(diagnostics?.version || "")}`, "ok");
    } catch (issue) {
      setEngineState("unavailable");
      setError(issue instanceof Error ? issue.message : String(issue));
    } finally { setBusy(""); }
  };

  const refreshRegistry = async () => {
    if (!workspace) { setError("Open or create a project before loading its institution registry."); return; }
    const result = await execute("workspace-hub", { action: "registry-list", workspace });
    const data = result && hubData<RegistryData>(result.events, "registry-list");
    if (data) {
      setRegistry(data.entities || []);
      setSelected(null);
      addActivity("Institution registry refreshed", `${data.count ?? data.entities?.length ?? 0} records · ${data.relationships ?? 0} relationships`, "ok");
    }
  };

  const createRequirement = async (event: FormEvent) => {
    event.preventDefault();
    if (!workspace) { setError("Open a project first."); setPage("project"); return; }
    const result = await execute("research-requirement", {
      workspace,
      question: question.trim(),
      geographies: geography,
      known_entities: knownEntities,
      target_audiences: audience,
    });
    if (result) {
      setRequirementSaved(true);
      addActivity("Research requirement saved", "The question and scope are in the project workspace.");
      setPage("project");
    }
  };

  const buildPlan = async () => {
    if (!workspace) return;
    const result = await execute("research-plan", { workspace, ai_expand: false });
    const reviewed = result && latestEvent<Record<string, unknown>>(result.events, "plan-review");
    if (reviewed) setPlan(reviewed);
    else if (result) setPlan({ message: "Plan generated and saved. Open Run history to review the complete backend output." });
  };

  const collectPlan = async () => {
    if (!workspace) return;
    const result = await execute("research-collect", { workspace });
    if (result) {
      addActivity("Research collection finished", "New source material is recorded in the project.", "ok");
      await refreshDashboard(workspace);
    }
  };

  const chooseEvidenceFile = async () => {
    if (!isTauri()) { evidenceInputRef.current?.click(); return; }
    const picked = await open({ multiple: false, title: "Choose evidence records to import", filters: [{ name: "Research data", extensions: ["csv", "jsonl", "ndjson"] }] });
    if (typeof picked === "string") setEvidenceFile(picked);
  };

  const uploadEvidenceFile = async (file?: File) => {
    if (!file || !workspace) return;
    setBusy("uploading-evidence");
    setError("");
    try {
      const uploaded = await uploadWorkspaceFile(workspace, file);
      setEvidenceFile(uploaded.path);
      addActivity("Evidence dataset uploaded", `${uploaded.name} · stored in the project workspace`, "ok");
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : String(issue));
    } finally { setBusy(""); }
  };

  const inspectEvidence = async (path = evidenceRecordsPath) => {
    if (!workspace || !path) return;
    const result = await execute("workspace-hub", { action: "dataset-browse", workspace, source_file: path, max_rows: 8 });
    const data = result && hubData<EvidencePreview>(result.events, "dataset-browse");
    if (data) setEvidencePreview(data);
  };

  const importEvidence = async () => {
    if (!workspace || !evidenceFile) return;
    const result = await execute("research-import", { workspace, source_file: evidenceFile, source_system: "analyst-import" });
    if (!result) return;
    const complete = latestEvent<{ outputs?: string[] }>(result.events, "complete");
    const imported = complete?.outputs?.find((item) => item.toLowerCase().endsWith(".jsonl"));
    if (imported) {
      setEvidenceRecordsPath(imported);
      setReviewPrepared(false);
      setEvidenceFile("");
      addActivity("Research records imported", `${evidenceFile.split(/[\\/]/).at(-1)} · ${imported.split(/[\\/]/).at(-1)}`, "ok");
      await inspectEvidence(imported);
      await refreshDashboard(workspace);
    } else {
      setError("The import completed, but SUGAR did not return the normalized records file.");
    }
  };

  const prepareEvidenceReview = async () => {
    if (!workspace || !evidenceRecordsPath) return;
    const result = await execute("research-prepare-review", { workspace, records_file: evidenceRecordsPath });
    const prepared = result && latestEvent<Record<string, unknown>>(result.events, "manual-review-ready");
    if (prepared) {
      setReviewPrepared(true);
      addActivity("Human review drafts prepared", `${prepared.records || 0} records are marked unreviewed.`, "ok");
      await refreshDashboard(workspace);
    }
  };

  const importFile = async () => {
    if (!isTauri()) { datasetInputRef.current?.click(); return; }
    const picked = await open({ multiple: false, title: "Choose a reference dataset", filters: [{ name: "Data files", extensions: ["csv", "tsv", "xlsx", "xls", "json", "jsonl"] }] });
    if (typeof picked !== "string") return;
    setDatasetFile(picked);
    const label = picked.split(/[\\/]/).at(-1) || "Reference dataset";
    setDatasetFileLabel(label);
    if (!datasetName) setDatasetName(label.replace(/\.[^.]+$/, "") || "Reference dataset");
    setPreview(null);
    setMappingText("{}");
  };

  const uploadRegistryFile = async (file?: File) => {
    if (!file || !workspace) return;
    setBusy("uploading-dataset");
    setError("");
    try {
      const uploaded = await uploadWorkspaceFile(workspace, file);
      setDatasetFile(uploaded.path);
      setDatasetFileLabel(uploaded.name);
      if (!datasetName) setDatasetName(uploaded.name.replace(/\.[^.]+$/, "") || "Reference dataset");
      setPreview(null);
      setMappingText("{}");
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : String(issue));
    } finally { setBusy(""); }
  };

  const previewImport = async () => {
    if (!datasetFile || !workspace) { setError("Choose a project and a dataset file before previewing."); return; }
    const result = await execute("workspace-hub", { action: "registry-preview", workspace, source_file: datasetFile });
    const data = result && hubData<RegistryPreview>(result.events, "registry-preview");
    if (data) {
      setPreview(data);
      setMappingText(JSON.stringify(data.suggested_mapping || {}, null, 2));
    }
  };

  const commitImport = async () => {
    if (!datasetFile || !workspace || !preview) return;
    try {
      const mapping = JSON.parse(mappingText) as Record<string, string>;
      const result = await execute("workspace-hub", {
        action: "registry-import", workspace, source_file: datasetFile, mapping,
        dataset_name: datasetName, network: datasetNetwork, accept_partial: false,
      });
      if (result) {
        setPreview(null);
        setDatasetFile("");
        setDatasetFileLabel("");
        await refreshRegistry();
      }
    } catch (issue) {
      setError(issue instanceof Error ? `Field mapping must be valid JSON: ${issue.message}` : "Field mapping must be valid JSON.");
    }
  };

  const exportHandoff = async () => {
    if (!workspace) { setError("Open a project before exporting a handoff."); return; }
    if (!evidenceRecordsPath || !reviewPrepared) { setError("Import research records and prepare the human-review draft before exporting a handoff."); return; }
    const suggested = `${projectName.trim().replace(/[^a-z0-9]+/gi, "-").toLowerCase() || "sugar-project"}-handoff.zip`;
    let outputDirectory: string;
    let name: string;
    if (isTauri()) {
      const output = await save({ title: "Export research handoff", defaultPath: suggested, filters: [{ name: "SUGAR handoff", extensions: ["zip"] }] });
      if (!output) return;
      const split = Math.max(output.lastIndexOf("/"), output.lastIndexOf("\\"));
      outputDirectory = split >= 0 ? output.slice(0, split) : workspace;
      name = output.slice(split + 1).replace(/\.zip$/i, "") || "sugar-handoff";
    } else {
      outputDirectory = `${workspace}/outputs/exports`;
      name = suggested.replace(/\.zip$/i, "");
    }
    const result = await execute("research-handoff", { workspace, output_directory: outputDirectory, name, records_file: evidenceRecordsPath });
    const completed = result && latestEvent<{ outputs?: string[] }>(result.events, "handoff-complete");
    const bundle = completed?.outputs?.[0];
    if (result && bundle) {
      const verified = await execute("research-handoff-verify", { bundle_directory: bundle });
      const verification = verified && latestEvent<Record<string, unknown>>(verified.events, "handoff-verified");
      if (verification?.status === "pass") {
        addActivity("Handoff exported and verified", `${outputDirectory}/${name}.zip · all bundle checks passed`, "ok");
      } else {
        const backendError = verified && latestEvent<Record<string, unknown>>(verified.events, "error");
        const message = String(backendError?.message || `The bundle was exported to ${bundle}, but its verification did not pass.`);
        setError(message);
        addActivity("Handoff verification failed", message, "error");
      }
      if (!isTauri() && verification?.status === "pass") {
        const archive = completed?.outputs?.find((item) => item.toLowerCase().endsWith(".zip"));
        if (archive) {
          try { await downloadWorkspaceFile(archive, `${name}.zip`); }
          catch (issue) { setError(issue instanceof Error ? issue.message : String(issue)); }
        }
      }
    }
  };

  const changePage = (next: Page) => {
    setError("");
    setPage(next);
    if (next === "institutions" && registry.length === 0 && workspace) void refreshRegistry();
  };

  const title = NAV.find((item) => item.id === page)?.label || "Settings";

  return (
    <div className="app-shell">
      <input ref={evidenceInputRef} className="sr-only" type="file" accept=".csv,.jsonl,.ndjson" onChange={(event) => { const file = event.currentTarget.files?.[0]; void uploadEvidenceFile(file); event.currentTarget.value = ""; }} />
      <input ref={datasetInputRef} className="sr-only" type="file" accept=".csv,.tsv,.xlsx,.xls,.json,.jsonl" onChange={(event) => { const file = event.currentTarget.files?.[0]; void uploadRegistryFile(file); event.currentTarget.value = ""; }} />
      <aside className="sidebar">
        <div className="brand-row"><div className="brand-mark">S</div><div><div className="brand-name">SUGAR</div><div className="brand-subtitle">Research workspace</div></div></div>
        <div className="side-caption">WORKSPACE</div>
        <nav className="nav-list" aria-label="Main navigation">
          {NAV.map((item) => <button key={item.id} className={`nav-item ${page === item.id ? "active" : ""}`} onClick={() => changePage(item.id)}><span className="nav-icon">{item.icon}</span>{item.label}{item.id === "activity" && activity.length > 0 && <span className="nav-count">{Math.min(activity.length, 99)}</span>}</button>)}
        </nav>
        <div className="side-caption secondary-caption">PROJECT</div>
        <button className="project-chip" onClick={() => changePage("project")}><span className={`project-indicator ${workspace ? "connected" : ""}`} /><span className="project-chip-copy"><strong>{projectName || "No project open"}</strong><small>{workspace ? workspace.split(/[\\/]/).at(-1) : "Choose a project folder"}</small></span><span className="chevron">›</span></button>
        <div className="sidebar-spacer" />
        <div className="engine-card"><div className={`engine-light ${engineState}`} /><div><strong>{engineState === "checking" ? "Connecting to engine" : engineState === "unavailable" ? "Engine unavailable" : engineState === "preview" ? "Browser preview" : isTauri() ? "Local research engine" : "SUGAR API connected"}</strong><small>{engineState === "ready" ? `Python core · ${engineVersion || "connected"}` : engineState === "unavailable" ? "Check the API address and credentials" : engineState === "preview" ? "Connect a research API to work" : "Checking Python core"}</small></div></div>
        <button className={`nav-item settings-link ${page === "settings" ? "active" : ""}`} onClick={() => changePage("settings")}><span className="nav-icon">⚙</span>Settings</button>
        <div className="sidebar-version">SUGAR Desktop <span>1.4</span></div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs"><span>SUGAR</span><b>/</b><strong>{title}</strong></div>
          <div className="topbar-actions"><div className={`connection-badge ${busy ? "working" : workspace ? "connected" : ""}`}><i />{busy ? `${titleCase(busy)} running` : workspace ? "Project connected" : "No project open"}</div><button className="button button-primary button-small" onClick={() => void chooseWorkspace()} disabled={Boolean(busy)}><span>＋</span> Open project</button></div>
        </header>

        {error && <div className="error-banner" role="alert"><span className="error-symbol">!</span><div><strong>Action needs attention</strong><p>{error}</p></div><button onClick={() => setError("")} aria-label="Dismiss error">×</button></div>}
        {busy && <div className="progress-line"><i /></div>}
        {workspacePickerOpen && <div className="workspace-picker-backdrop" onClick={() => setWorkspacePickerOpen(false)}><section className="workspace-picker" role="dialog" aria-modal="true" aria-labelledby="workspace-picker-title" onClick={(event) => event.stopPropagation()}><div className="workspace-picker-heading"><div><span className="eyebrow">SUGAR API</span><h2 id="workspace-picker-title">Choose a research project</h2><p>Projects are stored by the connected Python service.</p></div><button className="inspector-close" onClick={() => setWorkspacePickerOpen(false)} aria-label="Close project picker">×</button></div><div className="workspace-picker-list">{remoteWorkspaces.map((item) => <button className="workspace-option" key={item.id} onClick={() => openRemoteWorkspace(item)}><span className="project-current-mark">⌂</span><span><strong>{item.name}</strong><small>{item.description || "SUGAR project workspace"}</small></span><b>Open →</b></button>)}{!remoteWorkspaces.length && <div className="workspace-picker-empty"><span>⌂</span><strong>No projects on this API yet</strong><p>Create a project below to start a research workspace.</p></div>}</div><form className="workspace-create-form" onSubmit={(event) => void createRemoteWorkspace(event)}><label className="field-block"><span>New project name</span><input value={remoteProjectName} onChange={(event) => setRemoteProjectName(event.target.value)} maxLength={120} placeholder="e.g. Public diplomacy in Ghana" /></label><button className="button button-primary" type="submit" disabled={!remoteProjectName.trim() || Boolean(busy)}>Create project <span>→</span></button></form></section></div>}

        {page === "home" && <section className="page-content overview-page">
          <div className="page-heading"><div><div className="eyebrow">RESEARCH DESK <span className="eyebrow-line" /></div><h1>Good work starts with a clear question.</h1><p>A focused workspace for planning, collecting, and inspecting evidence.</p></div><div className="date-stamp">{new Date().toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}</div></div>
          {!workspace ? <div className="welcome-card"><div className="welcome-copy"><div className="welcome-tag"><span className="welcome-spark">✦</span> Your next step</div><h2>Open a project to get started</h2><p>{isTauri() ? "Create a local research space for your question, datasets, evidence, and exports." : "Connect to a SUGAR research service, then create or open a project in your browser."}</p><button className="button button-light" onClick={() => void chooseWorkspace()} disabled={Boolean(busy)}>Create or open project <span>→</span></button></div><div className="welcome-art" aria-hidden="true"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-sphere"><span>◎</span></div><div className="art-node node-a" /><div className="art-node node-b" /><div className="art-node node-c" /><div className="art-line line-a" /><div className="art-line line-b" /></div></div> : <div className="welcome-card project-welcome"><div className="welcome-copy"><div className="welcome-tag"><span className="welcome-spark">✦</span> Active project</div><h2>{projectName}</h2><p>{dashboard?.description || "Keep your research question, source data, institution registry, and handoff together in one portable project."}</p><div className="project-path"><span>⌁</span>{workspace.startsWith("sugar-workspace://") ? `Connected project · ${projectName}` : workspace}</div><div className="welcome-actions"><button className="button button-light" onClick={() => changePage("project")}>Continue research <span>→</span></button><button className="button button-dark-ghost" onClick={() => void exportHandoff()} disabled={Boolean(busy) || !evidenceRecordsPath || !reviewPrepared}>Export handoff</button></div></div><div className="welcome-art" aria-hidden="true"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-sphere"><span>◎</span></div><div className="art-node node-a" /><div className="art-node node-b" /><div className="art-node node-c" /><div className="art-line line-a" /><div className="art-line line-b" /></div></div>}
          <div className="metrics-grid">
            <Metric label="Institutions" value={workspace ? String(registry.length) : "—"} detail={`${locatedCount} with mapped coordinates`} icon="⌖" tone="blue" />
            <Metric label="Project artifacts" value={workspace ? String(dashboard?.artifact_count ?? 0) : "—"} detail={`${dashboard?.missing_artifacts ?? 0} registered files missing`} icon="▤" tone="green" />
            <Metric label="Project activity" value={workspace ? String(activity.length) : "—"} detail="Recorded research and workspace events" icon="↗" tone="violet" />
            <Metric label="Relationships" value={workspace ? String(registryRelationships) : "—"} detail="Documented institutional links" icon="⤳" tone="amber" />
          </div>
          <div className="home-lower"><div className="panel quick-start"><div className="panel-heading"><div><span className="eyebrow">WORKFLOW</span><h3>Build an evidence-backed project</h3></div><span className="heading-mark">4 steps</span></div><div className="step-list"><WorkflowStep number="01" title="State the research question" detail="Define scope and intended audience." done={requirementSaved} onClick={() => changePage("project")} /><WorkflowStep number="02" title="Bring in source material" detail="Import evidence or registry data." done={Boolean(evidenceRecordsPath || registry.length)} onClick={() => changePage("project")} /><WorkflowStep number="03" title="Inspect the plan and evidence" detail="Review search branches, records, and locations." done={Boolean(plan && evidencePreview)} onClick={() => changePage("project")} /><WorkflowStep number="04" title="Prepare a handoff" detail="Export a portable, reviewable bundle." done={reviewPrepared} onClick={() => void exportHandoff()} last /></div></div><div className="panel recent-panel"><div className="panel-heading"><div><span className="eyebrow">PROJECT ACTIVITY</span><h3>Recent work</h3></div><button className="text-button" onClick={() => changePage("activity")}>View history <span>→</span></button></div>{activity.length ? <div className="recent-list">{activity.slice(0, 4).map((item) => <ActivityRow key={item.id} item={item} />)}</div> : <div className="empty-inline"><span className="empty-icon">⌁</span><strong>No activity yet</strong><p>Project operations will appear here as they are completed.</p></div>}</div></div>
        </section>}

        {page === "project" && <section className="page-content">
          <div className="page-heading compact-heading"><div><div className="eyebrow">RESEARCH PROJECT <span className="eyebrow-line" /></div><h1>Define the work before collecting.</h1><p>Set the project home and create a research requirement that guides the evidence plan.</p></div><span className={`workflow-state ${workspace ? "ready" : "pending"}`}><i />{workspace ? "Project ready" : "Project required"}</span></div>
          <div className="project-layout"><div className="column-main">
            <div className="panel project-panel"><div className="section-title"><div className="section-icon blue">⌂</div><div><h3>Project workspace</h3><p>Your research stays organized in a portable folder or hosted project.</p></div></div><div className="project-current"><div className="project-current-mark">{workspace ? "✓" : "⌂"}</div><div className="project-current-main"><strong>{workspace ? projectName : "No active project"}</strong><span>{workspace ? workspace.startsWith("sugar-workspace://") ? `Hosted project · ${projectName}` : workspace : "Choose an existing project or create a new one."}</span></div><button className="button button-secondary" onClick={() => void chooseWorkspace()} disabled={Boolean(busy)}>{workspace ? "Change project" : "Choose project"}</button></div></div>
            <div className="panel requirement-panel"><div className="section-title"><div className="section-icon violet">⌕</div><div><h3>Research requirement</h3><p>A precise question gives the search plan a useful starting point.</p></div><span className="step-badge">STEP 1</span></div><form className="research-form" onSubmit={(event) => void createRequirement(event)}><label className="field-block"><span>Research question <em>Required</em></span><textarea value={question} onChange={(event) => setQuestion(event.target.value)} required rows={3} placeholder="What would you like to understand?" /></label><div className="field-grid"><label className="field-block"><span>Geographies</span><input value={geography} onChange={(event) => setGeography(event.target.value)} placeholder="Countries, regions, or cities" /><small>Separate multiple places with commas.</small></label><label className="field-block"><span>Known institutions or entities</span><input value={knownEntities} onChange={(event) => setKnownEntities(event.target.value)} placeholder="Names already in scope" /><small>Optional starting points for the plan.</small></label></div><label className="field-block"><span>Intended audience</span><input value={audience} onChange={(event) => setAudience(event.target.value)} placeholder="Who will use the results?" /></label><div className="form-footer"><span className="privacy-note"><span>◉</span> The requirement is saved in this project folder.</span><button className="button button-primary" type="submit" disabled={!workspace || !question.trim() || Boolean(busy)}>Save research requirement <span>→</span></button></div></form></div>
            <div className="panel evidence-panel"><div className="section-title"><div className="section-icon blue">▤</div><div><h3>Import and inspect research records</h3><p>Bring in an authorized CSV or JSONL dataset and inspect its source fields.</p></div><span className="step-badge">STEP 2</span></div><div className="evidence-import-row"><div className="evidence-file"><span className="file-mark">▧</span><div><strong>{evidenceFile ? evidenceFile.split(/[\\/]/).at(-1) : evidenceRecordsPath ? "Research records are in this project" : "No evidence dataset selected"}</strong><small>{evidenceRecordsPath || "Choose a CSV or JSONL file to begin an auditable import."}</small></div></div><div className="evidence-actions"><button className="button button-secondary" onClick={() => void chooseEvidenceFile()} disabled={!workspace || Boolean(busy)}>Choose data</button>{evidenceFile && <button className="button button-primary" onClick={() => void importEvidence()} disabled={Boolean(busy)}>Import records <span>→</span></button>}</div></div>{evidenceRecordsPath && <div className="evidence-review-row"><span className={`review-state ${reviewPrepared ? "ready" : "pending"}`}><i />{reviewPrepared ? "Human-review draft prepared" : "Imported · awaiting review draft"}</span><div className="evidence-actions"><button className="button button-quiet" onClick={() => void inspectEvidence()} disabled={Boolean(busy)}>Inspect records</button><button className="button button-secondary" onClick={() => void prepareEvidenceReview()} disabled={reviewPrepared || Boolean(busy)}>{reviewPrepared ? "Review draft ready" : "Prepare human review"}</button></div></div>}{evidencePreview && <div className="evidence-preview"><div className="preview-summary"><strong>{evidencePreview.row_count ?? 0} source records</strong><span>Showing {evidencePreview.rows?.length || 0} · source text and URL retained</span></div><div className="evidence-table-scroll"><table className="evidence-table"><thead><tr>{(evidencePreview.columns || []).filter((column) => ["platform", "author_name", "content_type", "original_text", "canonical_url", "source_url", "published_at", "query"].includes(column)).slice(0, 6).map((column) => <th key={column}>{titleCase(column)}</th>)}</tr></thead><tbody>{(evidencePreview.rows || []).map((row, index) => <tr key={String(row.record_key || row.native_id || index)}>{(evidencePreview.columns || []).filter((column) => ["platform", "author_name", "content_type", "original_text", "canonical_url", "source_url", "published_at", "query"].includes(column)).slice(0, 6).map((column) => <td key={column} title={String(row[column] ?? "")}>{String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table></div></div>}</div>
            <div className="panel plan-panel"><div className="section-title"><div className="section-icon green">☷</div><div><h3>Search plan</h3><p>Generate a deterministic first plan for review before any collection.</p></div><span className="step-badge">STEP 3</span></div><div className="plan-callout"><div className="plan-callout-copy"><strong>{plan ? "Plan ready to inspect" : "Plan only runs after the requirement is saved"}</strong><span>{plan ? `${Array.isArray(plan.branches) ? plan.branches.length : 0} search branches · no provider key required` : "You stay in control of what gets collected."}</span></div><button className="button button-secondary" onClick={() => void buildPlan()} disabled={!workspace || !requirementSaved || Boolean(busy)}>{plan ? "Refresh plan" : "Build research plan"} <span>→</span></button></div>{plan && <><div className="plan-preview">{Array.isArray(plan.branches) && plan.branches.length ? plan.branches.slice(0, 6).map((branch, index) => { const row = branch as Record<string, unknown>; return <div className="plan-branch" key={String(row.branch_id || index)}><span className="branch-number">{String(index + 1).padStart(2, "0")}</span><div><strong>{String(row.query || "Search branch")}</strong><p>{String(row.rationale || row.origin || "Review this line of inquiry before collection.")}</p></div><span className="branch-status">{titleCase(String(row.status || "proposed"))}</span></div>; }) : <p className="muted-copy">{String(plan.message || "Research plan generated.")}</p>}</div><div className="collection-footer"><span>Review the plan above, then start collection when ready.</span><button className="button button-primary" onClick={() => void collectPlan()} disabled={Boolean(busy)}>Run plan collection <span>→</span></button></div></>}</div>
          </div><aside className="column-side"><div className="side-note"><div className="note-mark">✧</div><span className="eyebrow">RESEARCH PRACTICE</span><h3>Keep the question visible.</h3><p>Every dataset, search, and analysis should trace back to a documented requirement. You can update it as the work evolves.</p><div className="note-separator" /><div className="note-stat"><strong>{requirementSaved ? "Saved" : "Not started"}</strong><span>Requirement status</span></div><div className="note-stat"><strong>{plan ? "Ready" : "Waiting"}</strong><span>Search plan status</span></div></div><div className="help-card"><span className="help-icon">i</span><div><strong>Review before collection</strong><p>The plan is a working proposal. Inspect its search branches before starting a collector run.</p></div></div></aside></div>
        </section>}

        {page === "institutions" && <section className="page-content institutions-page">
          <div className="page-heading compact-heading"><div><div className="eyebrow">REFERENCE REGISTRY <span className="eyebrow-line" /></div><h1>Institutions, on the map.</h1><p>Inspect locations, status, and sources from this project’s registry.</p></div><div className="heading-actions"><button className="button button-secondary" onClick={() => void importFile()} disabled={!workspace || Boolean(busy)}><span>＋</span> Import dataset</button><button className="button button-primary" onClick={() => void refreshRegistry()} disabled={!workspace || Boolean(busy)}><span>↻</span> Refresh registry</button></div></div>
          {preview && <div className="import-banner"><div className="import-intro"><div className="section-icon violet">⇧</div><div><strong>Review field mapping before import</strong><p>{datasetFileLabel || datasetFile.split(/[\\/]/).at(-1)} · {preview.row_count ?? "?"} source rows</p></div></div><div className="import-fields"><label className="field-block"><span>Dataset name</span><input value={datasetName} onChange={(event) => setDatasetName(event.target.value)} /></label><label className="field-block"><span>Institution network</span><input value={datasetNetwork} onChange={(event) => setDatasetNetwork(event.target.value)} placeholder="e.g. American Spaces" /></label></div><label className="field-block mapping-field"><span>Canonical field → source column <small>Adjust the suggested mapping where needed.</small></span><textarea className="mapping-text" value={mappingText} onChange={(event) => setMappingText(event.target.value)} rows={5} spellCheck={false} /></label><div className="import-footer"><span>Source: {preview.columns?.join(" · ") || "Detected columns"}</span><div><button className="button button-quiet" onClick={() => setPreview(null)}>Cancel</button><button className="button button-primary" onClick={() => void commitImport()} disabled={Boolean(busy)}>Import mapped records <span>→</span></button></div></div></div>}
          {datasetFile && !preview && <div className="pending-import"><span><strong>Dataset selected</strong> · {datasetFileLabel || datasetFile.split(/[\\/]/).at(-1)}</span><div><button className="button button-quiet" onClick={() => { setDatasetFile(""); setDatasetFileLabel(""); }}>Cancel</button><button className="button button-primary" onClick={() => void previewImport()} disabled={Boolean(busy)}>Preview field mapping <span>→</span></button></div></div>}
          <div className="registry-toolbar"><div className="search-field"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search institution, place, or network" /></div><label className="select-wrap"><span className="sr-only">Filter by network</span><select value={network} onChange={(event) => setNetwork(event.target.value)}>{networks.map((item) => <option key={item}>{item}</option>)}</select><b>⌄</b></label><label className="select-wrap"><span className="sr-only">Filter by status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>{["All statuses", "active", "closed", "proposed", "unknown"].map((item) => <option key={item}>{item}</option>)}</select><b>⌄</b></label><span className="registry-total"><strong>{filteredRows.length}</strong> of {registry.length}</span></div>
          <div className="registry-workspace"><div className="map-column"><div className="map-heading"><div><strong>Institution map</strong><span>Clustered locations · select a marker to inspect evidence</span></div><div className="map-tools"><span className="map-data-tag"><i /> {locatedCount} mapped</span></div></div>{workspace ? <InstitutionMap rows={filteredRows} onSelect={(id) => setSelected(registry.find((row) => row.entity_id === id) || null)} /> : <div className="map-empty"><span>⌖</span><strong>Open a project to view its registry map</strong><p>Institution locations will appear here when registry records are available.</p><button className="button button-primary" onClick={() => void chooseWorkspace()}>Open project</button></div>}</div><aside className="registry-side"><div className="registry-list-heading"><div><strong>Registry records</strong><span>{filteredRows.length} visible records</span></div><button className="icon-button" title="Refresh" onClick={() => void refreshRegistry()} disabled={!workspace || Boolean(busy)}>↻</button></div><div className="registry-list">{filteredRows.length ? filteredRows.slice(0, 300).map((row) => <button className={`registry-row ${selected?.entity_id === row.entity_id ? "selected" : ""}`} key={row.entity_id} onClick={() => setSelected(row)}><span className="institution-avatar">{(row.name || "?").slice(0, 1).toUpperCase()}</span><span className="institution-copy"><strong>{row.name || "Unnamed institution"}</strong><span>{[row.city, row.country].filter(Boolean).join(", ") || row.network || "Place not specified"}</span><small>{row.network || titleCase(row.entity_type || "Institution")}</small></span><span className={`status-dot status-${String(row.status || "unknown").toLowerCase()}`} /></button>) : <div className="list-empty"><span>⌖</span><strong>{registry.length ? "No matching institutions" : "No registry loaded"}</strong><p>{registry.length ? "Try a broader search or filter." : "Refresh the registry or import a reference dataset."}</p>{!registry.length && <button className="text-button" onClick={() => void refreshRegistry()} disabled={!workspace || Boolean(busy)}>Load registry →</button>}</div>}</div></aside></div>
          {selected && <div className="inspector-backdrop" onClick={() => setSelected(null)}><aside className="evidence-inspector" onClick={(event) => event.stopPropagation()}><div className="inspector-top"><div><span className="eyebrow">INSTITUTION RECORD</span><button className="inspector-close" onClick={() => setSelected(null)} aria-label="Close inspector">×</button></div><div className="inspector-identity"><div className="inspector-avatar">{(selected.name || "?").slice(0, 1).toUpperCase()}</div><div><h2>{selected.name || "Unnamed institution"}</h2><span>{[selected.city, selected.country].filter(Boolean).join(", ") || "Location not recorded"}</span></div></div><div className="inspector-badges"><span className={`status-pill status-pill-${String(selected.status || "unknown").toLowerCase()}`}>{titleCase(selected.status || "unknown")}</span><span className="network-pill">{selected.network || titleCase(selected.entity_type || "Institution")}</span></div></div><div className="inspector-content"><div className="inspector-section"><span className="eyebrow">PROFILE</span><p>{selected.description || "No descriptive profile has been recorded for this institution."}</p><div className="profile-facts"><div><span>Entity type</span><strong>{titleCase(selected.entity_type || "institution")}</strong></div><div><span>Coordinates</span><strong>{coordinatesText(selected)}</strong></div><div><span>Registry ID</span><strong>{selected.entity_id}</strong></div></div></div><div className="inspector-section"><div className="evidence-heading"><span className="eyebrow">EVIDENCE & SOURCES</span><span className="source-count">{extractEvidence(selected).length}</span></div>{extractEvidence(selected).length ? <div className="source-list">{extractEvidence(selected).map((source) => <a className="source-link" key={source.url} href={source.url} target="_blank" rel="noreferrer"><span className="source-icon">↗</span><span><strong>{source.label}</strong><small>{new URL(source.url).hostname}</small></span></a>)}</div> : <div className="evidence-gap"><span>◷</span><div><strong>Evidence gap</strong><p>No source URL has been attached yet. Verify this record before relying on its status or location.</p></div></div>}</div></div><div className="inspector-footer"><span>Claim-level source provenance is retained in the project registry.</span></div></aside></div>}
        </section>}

        {page === "activity" && <section className="page-content"><div className="page-heading compact-heading"><div><div className="eyebrow">AUDIT TRAIL <span className="eyebrow-line" /></div><h1>Project run history.</h1><p>Review the recent operations recorded for this workspace.</p></div><button className="button button-secondary" onClick={() => void refreshDashboard()} disabled={!workspace || Boolean(busy)}>↻ Refresh history</button></div><div className="panel history-panel"><div className="history-head"><div><strong>Recent project activity</strong><span>{activity.length} recorded events</span></div><div className="history-cols"><span>DETAIL</span><span>TIME</span></div></div>{activity.length ? activity.map((item) => <ActivityRow key={item.id} item={item} expanded />) : <div className="empty-state"><div className="empty-state-icon">↗</div><h3>No project history yet</h3><p>Research operations, imports, and exports will be recorded here.</p></div>}</div></section>}

        {page === "settings" && <section className="page-content"><div className="page-heading compact-heading"><div><div className="eyebrow">PREFERENCES <span className="eyebrow-line" /></div><h1>Connection settings.</h1><p>Connect the browser to a SUGAR Python service and manage optional provider credentials.</p></div><span className={`workflow-state ${engineState === "ready" ? "ready" : "pending"}`}><i />{engineState === "ready" ? "Engine connected" : "Connection needed"}</span></div><div className="settings-layout"><div className="panel settings-panel">{!isTauri() && <><div className="section-title"><div className="section-icon blue">↗</div><div><h3>Research API</h3><p>The same browser interface works with a local service or an approved hosted endpoint.</p></div></div><div className="api-connection-fields"><label className="field-block"><span>API address</span><input type="url" value={apiUrl} onChange={(event) => setApiUrl(event.target.value)} placeholder="http://127.0.0.1:8765" /></label><label className="field-block"><span>API token <small>Only needed when the service requires one</small></span><input type="password" autoComplete="off" value={apiToken} onChange={(event) => setApiToken(event.target.value)} placeholder="Session only" /></label><div className="api-connect-footer"><span>Use HTTPS for a remotely hosted API. The token stays in this browser session.</span><button className="button button-primary" onClick={() => void connectResearchEngine()} disabled={Boolean(busy)}>Test connection</button></div></div><div className="settings-divider" /></>}
          <div className="section-title"><div className="section-icon amber">⌘</div><div><h3>Provider credentials</h3><p>Credentials are sent only with the research operation that needs them.</p></div><span className="secure-badge"><span>◉</span> Session only</span></div><div className="credential-list">{SECRET_FIELDS.map(({ key, label, placeholder }) => <label className="field-block" key={key}><span>{label}</span><input type="password" autoComplete="off" value={credentials[key] || ""} onChange={(event) => setCredentials((current) => ({ ...current, [key]: event.target.value }))} placeholder={placeholder} /></label>)}</div><div className="settings-footnote"><span>i</span><p>Provider credentials stay in memory and are not written to a project or browser storage. Closing this app clears them. Remote API connections should use HTTPS.</p></div></div><aside className="connection-summary"><div className="summary-head"><span className="summary-icon">◉</span><div><strong>Research engine</strong><small>{isTauri() ? "Packaged Python sidecar" : "Python HTTP API"}</small></div></div><div className="summary-divider" /><div className="summary-row"><span>Interface</span><strong>Browser UI</strong></div><div className="summary-row"><span>Desktop wrapper</span><strong>Optional Tauri app</strong></div><div className="summary-row"><span>Project storage</span><strong>{isTauri() ? "Selected local folder" : "API workspace root"}</strong></div><div className="summary-map-note"><span>⌖</span><p>MapLibre uses OpenFreeMap vector tiles for the background map. Institution records remain in the project workspace.</p></div></aside></div></section>}

        <footer className="statusbar"><div><span className={`status-dot ${workspace ? "active" : "unknown"}`} /><span>{workspace ? `Workspace · ${workspace.split(/[\\/]/).at(-1)}` : "Local workspace not selected"}</span></div><span className="statusbar-right">SUGAR research engine <b>·</b> Python core</span></footer>
      </main>
    </div>
  );
}

function coordinatesText(row: Institution) {
  const point = institutionCoordinates(row);
  return point ? `${point[1].toFixed(4)}, ${point[0].toFixed(4)}` : "Not recorded";
}

function Metric({ label, value, detail, icon, tone }: { label: string; value: string; detail: string; icon: string; tone: string }) {
  return <div className="metric-card"><div className={`metric-icon ${tone}`}>{icon}</div><div className="metric-text"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div><span className="metric-trend">⌁</span></div>;
}

function WorkflowStep({ number, title, detail, done, onClick, last = false }: { number: string; title: string; detail: string; done: boolean; onClick: () => void; last?: boolean }) {
  return <button className={`workflow-step ${last ? "last" : ""}`} onClick={onClick}><span className={`step-index ${done ? "complete" : ""}`}>{done ? "✓" : number}</span><span className="step-copy"><strong>{title}</strong><small>{detail}</small></span><span className="step-arrow">→</span></button>;
}

function ActivityRow({ item, expanded = false }: { item: ActivityItem; expanded?: boolean }) {
  return <div className={`activity-row ${expanded ? "expanded" : ""}`}><span className={`activity-mark ${item.kind}`}><i /></span><div className="activity-copy"><strong>{item.title}</strong><span>{item.detail}</span></div><time>{item.time}</time></div>;
}
