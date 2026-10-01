import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";
import { api, configureApi, createWorkspace, defaultApiUrl, downloadWorkspaceFile, ensureLocalApi, hubData, issueMemberAccessToken, latestEvent, listWorkspaces, openLocalFolder, revokeMemberAccessToken, runBackend, uploadWorkspaceFile, type ApiWorkspace, type Credentials } from "./bridge";
import { InstitutionMap, institutionCoordinates } from "./map-view";
import type { BackendEvent, Institution } from "./types";
import { AboutPage } from "./about-page";
import { ActivityView } from "./activity-view";
import { usePrefs } from "./prefs";
import { Onboarding } from "./onboarding";
import { InstitutionsPage } from "./institutions-page";
import { MapPage } from "./map-page";
import { CommandPalette, ShortcutHelp, type Command } from "./command-palette";
import { ToastHost, type Toast } from "./ui";
import { ProjectsPage } from "./projects-page";
import { research } from "./research-api";
import { ResearchPage } from "./research-page";
import type { ProjectOverview, RunSummary } from "./research-types";
import { ResultsView } from "./results-view";
import { SettingsPage } from "./settings-page";
import { TimelinePage } from "./timeline-page";
import { StatusPill } from "./ui";

type Page = "research" | "activity" | "results" | "projects" | "network" | "map" | "home" | "project" | "institutions" | "timeline" | "settings" | "about";
type ActivityItem = { id: number; time: string; title: string; detail: string; kind: "ok" | "error" | "info" };
type Dashboard = {
  name?: string;
  description?: string;
  artifact_count?: number;
  missing_artifacts?: number;
  pending_review?: number;
  collection_issues?: number;
  artifacts?: Array<{ kind?: string; path?: string; external?: boolean; exists?: boolean }>;
  research_requirement?: {
    question?: string;
    geographies?: string[];
    known_entities?: string[];
    target_audiences?: string[];
    languages?: string[];
    excluded_topics?: string[];
    preferred_sources?: string[];
    notes?: string;
    timeframe?: { start?: string; end?: string };
  };
  search_plan?: Record<string, unknown>;
  research_strategy?: Record<string, unknown>;
  project_profile?: { notes?: string; members?: ProjectMember[]; access_control?: boolean };
};
type ProjectMember = { name: string; email: string; role: string };
type ResearchTemplate = { template_id: string; name: string; question?: string; geographies?: string[]; known_entities?: string[]; target_audiences?: string[]; languages?: string[]; excluded_topics?: string[]; preferred_sources?: string[]; since?: string; until?: string; notes?: string };
type ProjectComment = { comment_id: string; actor: string; body: string; created_at: string };
type ListeningMonitor = { monitor_id: string; name: string; status: string; cadence_minutes: number; next_due_at?: string; terms?: string[]; sources?: string[] };
type RegistryData = { entities?: Institution[]; count?: number; relationships?: number };
type RegistryPreview = { columns?: string[]; suggested_mapping?: Record<string, string>; sample_rows?: Record<string, unknown>[]; row_count?: number; [key: string]: unknown };
type EvidencePreview = { columns?: string[]; rows?: Record<string, unknown>[]; row_count?: number; matching_rows?: number };
type GeographySummary = { group_by?: string; total_rows?: number; located_rows?: number; unlocated_rows?: number; groups?: Array<{ label?: string; records?: number; share?: number }>; guardrail?: string };
type GeographyComparison = { group_by?: string; left_total?: number; right_total?: number; groups?: Array<{ label?: string; left_records?: number; right_records?: number; left_share?: number; right_share?: number; share_difference?: number }>; guardrail?: string };
type CollectionScope = {
  terms: string;
  sources: string;
  since: string;
  until: string;
  post_languages: string;
  excluded_topics: string;
};
const COLLECTION_SOURCES = ["x", "bluesky", "mastodon", "weibo", "bilibili"];

function commaList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

const NAV_BASIC: Array<{ id: Page; label: string; icon: string }> = [
  { id: "research", label: "Research", icon: "⌕" },
  { id: "activity", label: "Activity", icon: "↗" },
  { id: "results", label: "Results", icon: "▤" },
  { id: "network", label: "Institutions", icon: "◈" },
  { id: "map", label: "Map", icon: "⌖" },
  { id: "projects", label: "Projects", icon: "⌂" },
];
// Advanced mode adds the evidence, map, and audit surfaces.
const NAV_ADVANCED: Array<{ id: Page; label: string; icon: string }> = [
  { id: "home", label: "Overview", icon: "◫" },
  { id: "project", label: "Evidence & handoff", icon: "☷" },
  { id: "institutions", label: "Institutions & map", icon: "⌖" },
  { id: "timeline", label: "Project timeline", icon: "◷" },
];
const PAGE_TITLES: Record<Page, string> = {
  research: "Research", activity: "Activity", results: "Results", network: "Institutions", map: "Map", projects: "Projects", home: "Overview", project: "Evidence & handoff",
  institutions: "Institutions & map", timeline: "Project timeline", settings: "Settings", about: "About",
};

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
  const [page, setPage] = useState<Page>("research");
  const [prefs, savePrefs] = usePrefs();
  const [prefill, setPrefill] = useState<{ text: string; n: number }>({ text: "", n: 0 });
  const [showSetup, setShowSetup] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [openInstitution, setOpenInstitution] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);
  const notify = useCallback((text: string, tone: Toast["tone"] = "info", action?: Toast["action"]) => {
    const id = ++toastId.current;
    setToasts((current) => [...current.slice(-2), { id, tone, text, action }]);
    window.setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), action ? 9000 : 5000);
  }, []);
  const [workspace, setWorkspace] = useState(() => localStorage.getItem("sugar.workspace") || "");
  const [projectId, setProjectId] = useState(() => localStorage.getItem("sugar.projectId") || "");
  const [projects, setProjects] = useState<ApiWorkspace[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [overview, setOverview] = useState<ProjectOverview | null>(null);
  const [runId, setRunId] = useState("");
  const [timelineKey, setTimelineKey] = useState(0);
  const [createSignal, setCreateSignal] = useState(0);
  const settingsDirty = useRef(false);
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
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  // Credentials are managed in Settings and stored securely by the engine; operations resolve them there.
  const credentials = useMemo<Credentials>(() => ({}), []);
  const [question, setQuestion] = useState("");
  const [geography, setGeography] = useState("");
  const [knownEntities, setKnownEntities] = useState("");
  const [projectNotes, setProjectNotes] = useState("");
  const [projectContextNotes, setProjectContextNotes] = useState("");
  const [projectMembers, setProjectMembers] = useState<ProjectMember[]>([]);
  const [projectComments, setProjectComments] = useState<ProjectComment[]>([]);
  const [commentDraft, setCommentDraft] = useState("");
  const [commentAuthor, setCommentAuthor] = useState("Analyst");
  const [researchTemplates, setResearchTemplates] = useState<ResearchTemplate[]>([]);
  const [selectedResearchTemplate, setSelectedResearchTemplate] = useState("");
  const [researchTemplateName, setResearchTemplateName] = useState("");
  const [listeningMonitors, setListeningMonitors] = useState<ListeningMonitor[]>([]);
  const [monitorName, setMonitorName] = useState("");
  const [monitorTerms, setMonitorTerms] = useState("");
  const [monitorSources, setMonitorSources] = useState("x");
  const [monitorCadence, setMonitorCadence] = useState("1440");
  const [monitorGeographies, setMonitorGeographies] = useState("");
  const [memberAccessToken, setMemberAccessToken] = useState("");
  const [memberAccessMessage, setMemberAccessMessage] = useState("");
  const [audience, setAudience] = useState("Policy researchers");
  const [languages, setLanguages] = useState("auto");
  const [excludedTopics, setExcludedTopics] = useState("");
  const [preferredSources, setPreferredSources] = useState("");
  const [timeframeStart, setTimeframeStart] = useState("");
  const [timeframeEnd, setTimeframeEnd] = useState("");
  const [requirementSaved, setRequirementSaved] = useState(false);
  const [plan, setPlan] = useState<Record<string, unknown> | null>(null);
  const [strategy, setStrategy] = useState<Record<string, unknown> | null>(null);
  const [translatePosts, setTranslatePosts] = useState(false);
  const [inferLocations, setInferLocations] = useState(false);
  const [platformTuning, setPlatformTuning] = useState<Record<string, { max_posts_per_query: string; max_pages_per_query: string }>>({});
  const [activeCollectionRunId, setActiveCollectionRunId] = useState("");
  const [collectionScope, setCollectionScope] = useState<CollectionScope>({
    terms: "", sources: "", since: "", until: "", post_languages: "", excluded_topics: "",
  });
  const [collectionRetrySource, setCollectionRetrySource] = useState("x");
  const [collectionControlBusy, setCollectionControlBusy] = useState(false);
  const [collectionControlMessage, setCollectionControlMessage] = useState("");
  const [evidenceFile, setEvidenceFile] = useState("");
  const [publicItemSource, setPublicItemSource] = useState("weibo");
  const [publicItemUrl, setPublicItemUrl] = useState("");
  const [mastodonHashtag, setMastodonHashtag] = useState("");
  const [evidenceRecordsPath, setEvidenceRecordsPath] = useState("");
  const [evidenceMapPath, setEvidenceMapPath] = useState("");
  const [evidencePreview, setEvidencePreview] = useState<EvidencePreview | null>(null);
  const [codedFindingsPath, setCodedFindingsPath] = useState("");
  const [codedFindingsPreview, setCodedFindingsPreview] = useState<EvidencePreview | null>(null);
  const [evidenceExportFormat, setEvidenceExportFormat] = useState("csv");
  const [geographyGroupBy, setGeographyGroupBy] = useState("auto");
  const [geographySummary, setGeographySummary] = useState<GeographySummary | null>(null);
  const [geographyComparisonFile, setGeographyComparisonFile] = useState("");
  const [geographyComparison, setGeographyComparison] = useState<GeographyComparison | null>(null);
  const [geographyAssignmentRow, setGeographyAssignmentRow] = useState("0");
  const [geographyAssignmentCountry, setGeographyAssignmentCountry] = useState("");
  const [geographyAssignmentRegion, setGeographyAssignmentRegion] = useState("");
  const [geographyAssignmentCity, setGeographyAssignmentCity] = useState("");
  const [geographyAssignmentNote, setGeographyAssignmentNote] = useState("");
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
      const quietHubAction = operation === "workspace-hub" && ["dashboard", "project-history", "registry-list", "project-comment-list", "monitor-list", "research-template-list"].includes(String(config?.action || ""));
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
      const evidence = (data.artifacts || []).find((item) =>
        item.exists !== false && (
          (item.kind === "import" && item.path?.toLowerCase().endsWith(".jsonl")) ||
          (item.kind === "raw_collection" && item.path?.toLowerCase().endsWith(".csv"))
        )
      );
      setEvidenceRecordsPath(evidence ? evidence.external ? evidence.path || "" : `${path}/${evidence.path || ""}` : "");
      setReviewPrepared(Boolean(data.artifacts?.some((item) => item.kind === "observations")));
      const requirement = data.research_requirement;
      if (requirement) {
        setQuestion(String(requirement.question || ""));
        setProjectNotes(String(requirement.notes || ""));
        setGeography(Array.isArray(requirement.geographies) ? requirement.geographies.join(", ") : "");
        setKnownEntities(Array.isArray(requirement.known_entities) ? requirement.known_entities.join(", ") : "");
        setAudience(Array.isArray(requirement.target_audiences) ? requirement.target_audiences.join(", ") : "");
        setLanguages(Array.isArray(requirement.languages) ? requirement.languages.join(", ") : "auto");
        setExcludedTopics(Array.isArray(requirement.excluded_topics) ? requirement.excluded_topics.join(", ") : "");
        setPreferredSources(Array.isArray(requirement.preferred_sources) ? requirement.preferred_sources.join(", ") : "");
        setTimeframeStart(String(requirement.timeframe?.start || ""));
        setTimeframeEnd(String(requirement.timeframe?.end || ""));
      }
      setRequirementSaved(Boolean(requirement || data.artifacts?.some((item) => item.kind === "research_requirement")));
      setPlan(data.search_plan && typeof data.search_plan === "object" ? data.search_plan : null);
      setStrategy(data.research_strategy && typeof data.research_strategy === "object" ? data.research_strategy : null);
      setProjectContextNotes(String(data.project_profile?.notes || ""));
      setProjectMembers(Array.isArray(data.project_profile?.members) ? data.project_profile.members : []);
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
    try {
      const commentsResult = await runBackend("workspace-hub", { action: "project-comment-list", workspace: path }, {});
      const commentsData = hubData<{ comments?: ProjectComment[] }>(commentsResult.events, "project-comment-list");
      setProjectComments(commentsData?.comments || []);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : String(issue));
    }
  }, [workspace, execute]);

  // The legacy evidence/registry dashboard spawns several engine operations; load it only when one of its pages is opened.
  const legacyLoaded = useRef("");
  useEffect(() => {
    if (!workspace || !["home", "project", "institutions"].includes(page) || legacyLoaded.current === workspace) return;
    legacyLoaded.current = workspace;
    void refreshDashboard(workspace);
  }, [workspace, page]);

  useEffect(() => {
    let active = true;
    setEngineState("checking");
    // Desktop: start the loopback research API first; live runs and the research workbench use it.
    void ensureLocalApi().then(() => runBackend("diagnostics", undefined, credentials)).then((result) => {
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

  // ---- projects (research workbench) ------------------------------------------------------------------
  const loadProjects = useCallback(async () => {
    setProjectsLoading(true);
    try { setProjects(await listWorkspaces()); } catch (issue) { setError(issue instanceof Error ? issue.message : String(issue)); } finally { setProjectsLoading(false); }
  }, []);

  const refreshOverview = useCallback(async (id = projectId) => {
    if (!id) { setOverview(null); return; }
    try {
      const data = await research.overview(id);
      setOverview(data);
      setProjectName(data.summary.name);
      setRunId((current) => (current && data.runs.some((r) => r.run_id === current) ? current : data.runs[0]?.run_id || ""));
      setTimelineKey((n) => n + 1);
    } catch (issue) {
      const message = issue instanceof Error ? issue.message : String(issue);
      if (/not found/i.test(message)) { setProjectId(""); setOverview(null); } else setError(message);
    }
  }, [projectId]);

  const activateProject = useCallback((project: ApiWorkspace) => {
    setProjectId(project.id);
    setProjectName(project.name);
    // Browser projects are addressed by reference; the desktop app also knows the folder for its file dialogs.
    const reference = isTauri() ? (project.path || "") : project.workspace;
    setWorkspace(reference);
    try { localStorage.setItem("sugar.projectId", project.id); localStorage.setItem("sugar.workspace", reference); } catch { /* storage may be unavailable */ }
    setRunId("");
    setOverview(null);
  }, []);

  const changePage = useCallback((next: Page) => {
    if (page === "settings" && next !== "settings" && settingsDirty.current && !window.confirm("You have unsaved settings. Leave without saving them?")) return;
    setError("");
    setPage(next);
    if (next === "projects") void loadProjects();
    if (next === "institutions" && registry.length === 0 && workspace) void refreshRegistry();
  }, [page, loadProjects, registry.length, workspace]);

  const openProject = (project: ApiWorkspace) => {
    activateProject(project);
    addActivity("Project opened", project.name, "ok");
    setPage("research");
  };

  const createProject = async (name: string, question = ""): Promise<string> => {
    setBusy("creating-project");
    setError("");
    try {
      const created = await createWorkspace(name, question);
      setProjects((items) => [created, ...items]);
      activateProject(created);
      if (isTauri()) { const listed = (await listWorkspaces()).find((item) => item.id === created.id); if (listed?.path) { setWorkspace(listed.path); localStorage.setItem("sugar.workspace", listed.path); } }
      if (question) await api(`/api/workspaces/${created.id}/research/requirement`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: question }) }).catch(() => undefined);
      addActivity("Project created", name, "ok");
      setPage("research");
      return created.id;
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : String(issue));
      throw issue;
    } finally { setBusy(""); }
  };

  const openFolder = async () => {
    const selectedPath = await open({ directory: true, multiple: false, title: "Select a SUGAR project folder" });
    if (typeof selectedPath !== "string") return;
    setBusy("workspace-status");
    try {
      const linked = await openLocalFolder(selectedPath, true, projectName.trim() || "Research project");
      activateProject({ ...linked, path: selectedPath });
      addActivity("Project opened", linked.name, "ok");
      setPage("research");
    } catch (issue) { setError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };

  const ensureProject = async (suggested: string): Promise<string> => {
    if (projectId) return projectId;
    const name = suggested.trim() ? suggested.trim().replace(/^./, (c) => c.toUpperCase()) : "New research project";
    return createProject(name.slice(0, 120));
  };

  const handleRunStarted = useCallback((id: string, run: RunSummary) => {
    setRunId(run.run_id);
    setPage("activity");
    void refreshOverview(id);
  }, [refreshOverview]);

  const chooseWorkspace = () => changePage("projects");

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

  const moveInstitution = async (id: string, latitude: number, longitude: number) => {
    if (!workspace || latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return;
    const institution = registry.find((row) => row.entity_id === id);
    if (!institution) return;
    const result = await execute("workspace-hub", {
      action: "registry-upsert", workspace,
      entity: { ...institution, latitude, longitude },
      actor: "Analyst", reason: "Analyst adjusted the institution location on the project map.",
      review_state: "unreviewed",
    });
    const updated = result && hubData<Institution>(result.events, "registry-upsert");
    if (updated) {
      setSelected(updated);
      await refreshRegistry();
      addActivity("Institution location updated", "Map coordinates were saved for analyst review.", "info");
    }
  };

  const createRequirement = async (event: FormEvent) => {
    event.preventDefault();
    if (!workspace) { setError("Open a project first."); setPage("project"); return; }
    const result = await execute("research-requirement", {
      workspace,
      question: question.trim(),
      notes: projectNotes.trim(),
      geographies: geography,
      known_entities: knownEntities,
      target_audiences: audience,
      languages: commaList(languages),
      excluded_topics: commaList(excludedTopics),
      preferred_sources: commaList(preferredSources),
      since: timeframeStart,
      until: timeframeEnd,
    });
    if (result) {
      setRequirementSaved(true);
      addActivity("Research requirement saved", "The question and scope are in the project workspace.");
      setPage("project");
    }
  };

  const saveProjectProfile = async () => {
    if (!workspace) return;
    const result = await execute("workspace-hub", {
      action: "project-profile-update", workspace,
      notes: projectContextNotes,
      members: projectMembers,
    });
    const profile = result && hubData<{ notes?: string; members?: ProjectMember[] }>(result.events, "project-profile-update");
    if (profile) {
      setProjectContextNotes(String(profile.notes || ""));
      setProjectMembers(profile.members || []);
      addActivity("Project profile saved", `${profile.members?.length || 0} roster entries recorded.`, "ok");
    }
  };

  const addProjectMember = () => setProjectMembers((members) => [...members, { name: "", email: "", role: "Analyst" }]);

  const updateProjectMember = (index: number, field: keyof ProjectMember, value: string) => {
    setProjectMembers((members) => members.map((member, current) => current === index ? { ...member, [field]: value } : member));
  };

  const issueProjectMemberAccess = async (email: string) => {
    if (!workspace || isTauri()) return;
    try {
      const result = await issueMemberAccessToken(workspace, email);
      setMemberAccessToken(result.token);
      setMemberAccessMessage(`One-time ${result.role} token created for ${result.email}. Copy it now and share it through your approved secure channel.`);
    } catch (issue) {
      const message = issue instanceof Error ? issue.message : String(issue);
      setMemberAccessMessage(message);
      setError(message);
    }
  };

  const revokeProjectMemberAccess = async (email: string) => {
    if (!workspace || isTauri()) return;
    try {
      const result = await revokeMemberAccessToken(workspace, email);
      setMemberAccessMessage(result.revoked ? `Revoked ${result.revoked} access token(s) for ${email}.` : `No active access token was found for ${email}.`);
      setMemberAccessToken("");
    } catch (issue) {
      const message = issue instanceof Error ? issue.message : String(issue);
      setMemberAccessMessage(message);
      setError(message);
    }
  };

  const loadProjectComments = async () => {
    if (!workspace) return;
    try {
      const result = await runBackend("workspace-hub", { action: "project-comment-list", workspace }, {});
      const data = hubData<{ comments?: ProjectComment[] }>(result.events, "project-comment-list");
      setProjectComments(data?.comments || []);
    } catch (issue) {
      const message = issue instanceof Error ? issue.message : String(issue);
      setError(message);
    }
  };

  const addProjectComment = async () => {
    if (!workspace || !commentDraft.trim()) return;
    const result = await execute("workspace-hub", {
      action: "project-comment-add", workspace, body: commentDraft, actor: commentAuthor,
    });
    const comment = result && hubData<ProjectComment>(result.events, "project-comment-add");
    if (comment) {
      setProjectComments((items) => [...items, comment].slice(-100));
      setCommentDraft("");
      addActivity("Project comment added", `Added by ${comment.actor}.`, "ok");
    }
  };

  const loadResearchTemplates = async () => {
    if (!workspace) return;
    const result = await execute("workspace-hub", { action: "research-template-list", workspace });
    const data = result && hubData<{ templates?: ResearchTemplate[] }>(result.events, "research-template-list");
    if (data) {
      setResearchTemplates(data.templates || []);
      setSelectedResearchTemplate((current) => current || data.templates?.[0]?.template_id || "");
    }
  };

  const applyResearchTemplate = () => {
    const template = researchTemplates.find((item) => item.template_id === selectedResearchTemplate);
    if (!template) return;
    setQuestion(template.question || "");
    setGeography((template.geographies || []).join(", "));
    setKnownEntities((template.known_entities || []).join(", "));
    setAudience((template.target_audiences || []).join(", "));
    setLanguages((template.languages || ["auto"]).join(", "));
    setExcludedTopics((template.excluded_topics || []).join(", "));
    setPreferredSources((template.preferred_sources || []).join(", "));
    setTimeframeStart(template.since || "");
    setTimeframeEnd(template.until || "");
    setProjectNotes(template.notes || "");
    setRequirementSaved(false);
    setPlan(null);
    setStrategy(null);
  };

  const saveResearchTemplate = async () => {
    if (!workspace || !researchTemplateName.trim()) return;
    const result = await execute("workspace-hub", {
      action: "research-template-save", workspace, name: researchTemplateName,
      fields: {
        question, geographies: commaList(geography), known_entities: commaList(knownEntities),
        target_audiences: commaList(audience), languages: commaList(languages),
        excluded_topics: commaList(excludedTopics), preferred_sources: commaList(preferredSources),
        since: timeframeStart, until: timeframeEnd, notes: projectNotes,
      },
    });
    const template = result && hubData<ResearchTemplate>(result.events, "research-template-save");
    if (template) {
      setResearchTemplates((items) => [...items.filter((item) => item.name.toLowerCase() !== template.name.toLowerCase()), template]);
      setSelectedResearchTemplate(template.template_id);
      setResearchTemplateName("");
    }
  };

  const loadListeningMonitors = async () => {
    if (!workspace) return;
    const result = await execute("workspace-hub", { action: "monitor-list", workspace });
    const data = result && hubData<ListeningMonitor[]>(result.events, "monitor-list");
    if (Array.isArray(data)) setListeningMonitors(data);
  };

  const saveListeningMonitor = async () => {
    if (!workspace || !monitorName.trim() || !monitorTerms.trim() || !commaList(monitorSources).length) return;
    const result = await execute("workspace-hub", {
      action: "monitor-save", workspace, name: monitorName.trim(),
      terms: monitorTerms.split(/\r?\n/).map((value) => value.trim()).filter(Boolean),
      sources: commaList(monitorSources), geographies: commaList(monitorGeographies),
      cadence_minutes: Number(monitorCadence),
    });
    const monitor = result && hubData<ListeningMonitor>(result.events, "monitor-save");
    if (monitor) {
      setMonitorName("");
      setMonitorTerms("");
      await loadListeningMonitors();
    }
  };

  const setListeningMonitorStatus = async (monitor: ListeningMonitor) => {
    if (!workspace) return;
    const status = monitor.status === "active" ? "paused" : "active";
    const result = await execute("workspace-hub", { action: "monitor-status", workspace, monitor_id: monitor.monitor_id, status });
    if (result) await loadListeningMonitors();
  };

  const runDueListeningMonitors = async () => {
    if (!workspace) return;
    const result = await execute("workspace-hub", { action: "monitor-run-due", workspace, max_monitors: 10 });
    const summary = result && hubData<{ due_count?: number; run_count?: number; runs?: Array<{ status?: string; error?: string }> }>(result.events, "monitor-run-due");
    if (summary) addActivity("Scheduled listening checks completed", `${summary.run_count || 0} ran from ${summary.due_count || 0} due check(s).`, "ok");
    await loadListeningMonitors();
  };

  const interpretRequirement = async () => {
    if (!workspace) return;
    const result = await execute("research-compile", { workspace, ai_expand: true });
    const reviewed = result && latestEvent<Record<string, unknown>>(result.events, "strategy-review");
    if (reviewed) {
      setStrategy(reviewed);
      addActivity("AI interpretation ready", "Review the explicit concepts, interpretation, and hypotheses before approval.", "info");
    }
  };

  const approveInterpretation = async () => {
    if (!workspace) return;
    const result = await execute("research-strategy-update", {
      workspace, decision: "approved", reviewer: "Project analyst",
      review_note: "Reviewed the explicit source spans, interpretations, and hypotheses.",
    });
    const reviewed = result && latestEvent<Record<string, unknown>>(result.events, "strategy-review");
    if (reviewed) setStrategy(reviewed);
  };

  const buildPlan = async () => {
    if (!workspace) return;
    const result = await execute("research-plan", { workspace, ai_expand: false });
    const reviewed = result && latestEvent<Record<string, unknown>>(result.events, "plan-review");
    if (reviewed) setPlan(reviewed);
    else if (result) setPlan({ message: "Plan generated and saved. Open Run history to review the complete backend output." });
  };

  const collectionControlPayload = (): Omit<CollectionScope, "terms" | "sources" | "post_languages" | "excluded_topics"> & {
    terms: string[]; sources: string[]; post_languages: string[]; excluded_topics: string[];
  } => ({
    ...collectionScope,
    terms: collectionScope.terms.split(/\r?\n/).map((term) => term.trim()).filter(Boolean),
    sources: commaList(collectionScope.sources),
    post_languages: commaList(collectionScope.post_languages).filter((language) => language.toLowerCase() !== "auto"),
    excluded_topics: commaList(collectionScope.excluded_topics),
  });

  const sendCollectionControl = async (extra: Record<string, unknown> = {}) => {
    if (!workspace || !activeCollectionRunId) return false;
    setCollectionControlBusy(true);
    setCollectionControlMessage("Sending the update to the active run…");
    try {
      const config = extra.cancel
        ? { workspace, collection_run_id: activeCollectionRunId, cancel: true }
        : { workspace, collection_run_id: activeCollectionRunId, ...collectionControlPayload(), ...extra };
      const result = await runBackend("research-collect-control", config, {});
      const updated = latestEvent<Record<string, unknown>>(result.events, "collection-control-updated");
      if (extra.cancel) {
        setCollectionControlMessage("Stop requested. The current network request will finish first.");
      } else if (updated) {
        setCollectionControlMessage(`Update ${String(updated.revision || "")} queued for the next request boundary.`);
      } else {
        setCollectionControlMessage("Update sent. It will apply at the next request boundary.");
      }
      return true;
    } catch (issue) {
      const message = issue instanceof Error ? issue.message : String(issue);
      setCollectionControlMessage(message);
      setError(message);
      return false;
    } finally {
      setCollectionControlBusy(false);
    }
  };

  const startLiveCollection = async () => {
    if (!workspace || busy) return;
    const branches = Array.isArray(plan?.branches) ? plan.branches as Array<Record<string, unknown>> : [];
    const terms = branches
      .filter((branch) => !["completed", "paused", "skipped"].includes(String(branch.status || "").toLowerCase()))
      .map((branch) => String(branch.query || "").trim())
      .filter(Boolean);
    const initialScope: CollectionScope = {
      terms: terms.join("\n"),
      sources: preferredSources,
      since: timeframeStart,
      until: timeframeEnd,
      post_languages: commaList(languages).filter((language) => language.toLowerCase() !== "auto").join(", "),
      excluded_topics: excludedTopics,
    };
    const runId = crypto.randomUUID().replaceAll("-", "");
    const controlPayload = {
      workspace,
      collection_run_id: runId,
      start: true,
      terms,
      sources: commaList(initialScope.sources),
      since: initialScope.since,
      until: initialScope.until,
      post_languages: commaList(initialScope.post_languages),
      excluded_topics: commaList(initialScope.excluded_topics),
      translate_posts: translatePosts,
      infer_locations: inferLocations,
      platform_tuning: Object.fromEntries(Object.entries(platformTuning)
        .map(([source, limits]) => [source, Object.fromEntries(Object.entries(limits)
          .filter(([, value]) => value.trim())
          .map(([key, value]) => [key, Number(value)]))])
        .filter(([, limits]) => Object.keys(limits as Record<string, number>).length)),
    };

    setBusy("research-collect");
    setError("");
    setCollectionScope(initialScope);
    setCollectionRetrySource(commaList(initialScope.sources)[0] || "x");
    setCollectionControlMessage("Preparing run controls…");
    try {
      await runBackend("research-collect-control", controlPayload, {});
      setActiveCollectionRunId(runId);
      setCollectionControlMessage("Live updates apply between source requests; an in-flight request is allowed to finish.");
      const collectionConfig = Object.fromEntries(Object.entries(controlPayload).filter(([key]) => key !== "start"));
      const result = await runBackend("research-collect", collectionConfig, credentials);
      const collectionComplete = latestEvent<{ outputs?: string[] }>(result.events, "complete");
      const collected = collectionComplete?.outputs?.find((item) => item.toLowerCase().endsWith(".csv"));
      if (collected) {
        setEvidenceRecordsPath(collected);
        setEvidenceMapPath("");
        setReviewPrepared(false);
        await inspectEvidence(collected);
      }
      for (const event of result.events) {
        const item = summarizeEvent(event);
        if (item.title !== "Research engine ready" && item.title !== "Operation complete") {
          addActivity(item.title, item.detail, event.event === "error" ? "error" : "info");
        }
      }
      const stopped = result.events.some((event) => event.event === "collection_stopped");
      addActivity(
        stopped ? "Research collection stopped" : "Research collection finished",
        stopped ? "Partial results were saved after the current request completed." : "New source material is recorded in the project.",
        "ok",
      );
      setCollectionControlMessage(stopped ? "Run stopped. Partial results were saved." : "Run complete.");
      setBusy("");
      setActiveCollectionRunId("");
      await refreshDashboard(workspace);
    } catch (issue) {
      const message = issue instanceof Error ? issue.message : String(issue);
      setError(message);
      setCollectionControlMessage(message);
      addActivity("Research collection", message, "error");
      setBusy("");
      setActiveCollectionRunId("");
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
      setEvidenceMapPath("");
      setReviewPrepared(false);
      setEvidenceFile("");
      addActivity("Research records imported", `${evidenceFile.split(/[\\/]/).at(-1)} · ${imported.split(/[\\/]/).at(-1)}`, "ok");
      await inspectEvidence(imported);
      await refreshDashboard(workspace);
    } else {
      setError("The import completed, but SUGAR did not return the normalized records file.");
    }
  };

  const importPublicItem = async () => {
    if (!workspace || !publicItemUrl.trim()) return;
    const result = await execute("ingest", {
      workspace, source: publicItemSource, identifier: publicItemUrl.trim(),
    });
    const complete = result && latestEvent<{ outputs?: string[] }>(result.events, "complete");
    const collected = complete?.outputs?.find((item) => item.toLowerCase().endsWith(".csv"));
    if (!collected) return;
    setEvidenceRecordsPath(collected);
    setEvidenceMapPath("");
    setReviewPrepared(false);
    setPublicItemUrl("");
    await inspectEvidence(collected);
    await refreshDashboard(workspace);
    addActivity("Public item collected", `${titleCase(publicItemSource)} item saved with source provenance.`, "ok");
  };

  const collectPublicHashtag = async () => {
    if (!workspace) return;
    const tag = mastodonHashtag.trim();
    if (!/^#[^\s#]+$/.test(tag)) {
      setError("Enter one Mastodon hashtag, such as #education.");
      return;
    }
    const result = await execute("search", {
      workspace, sources: ["mastodon"], terms: [tag],
      max_posts_per_query: 20, max_pages_per_query: 1,
      translate_posts: false, infer_locations: false,
    });
    const complete = result && latestEvent<{ outputs?: string[] }>(result.events, "complete");
    const collected = complete?.outputs?.find((item) => item.toLowerCase().endsWith(".csv"));
    if (!collected) return;
    setEvidenceRecordsPath(collected);
    setEvidenceMapPath("");
    setReviewPrepared(false);
    await inspectEvidence(collected);
    await refreshDashboard(workspace);
    addActivity("Mastodon hashtag collected", `${tag} saved as project evidence.`, "ok");
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

  const codeEvidence = async () => {
    if (!workspace || !evidenceRecordsPath) return;
    const result = await execute("research-triage", { workspace, records_file: evidenceRecordsPath });
    const completed = result && latestEvent<{ outputs?: string[] }>(result.events, "triage-complete");
    const output = completed?.outputs?.find((item) => item.toLowerCase().endsWith(".csv"));
    if (!output) return;
    setCodedFindingsPath(output);
    const browse = await execute("workspace-hub", {
      action: "dataset-browse", workspace, source_file: output, max_rows: 100,
    });
    const data = browse && hubData<EvidencePreview>(browse.events, "dataset-browse");
    if (data) {
      setCodedFindingsPreview(data);
      addActivity("Coded findings generated", `${data.row_count || 0} AI-triaged records are ready for human review.`, "info");
    }
  };

  const exportEvidence = async () => {
    if (!workspace || !evidenceRecordsPath) return;
    const fileName = `${projectName.trim().replace(/[^a-z0-9]+/gi, "-").toLowerCase() || "sugar-project"}-evidence.${evidenceExportFormat}`;
    let outputFile: string | undefined;
    if (isTauri()) {
      outputFile = await save({
        title: "Export research records",
        defaultPath: fileName,
        filters: [{ name: `${evidenceExportFormat.toUpperCase()} dataset`, extensions: [evidenceExportFormat] }],
      }) || undefined;
      if (!outputFile) return;
    }
    const result = await execute("workspace-hub", {
      action: "dataset-export", workspace, source_file: evidenceRecordsPath,
      format: evidenceExportFormat, file_name: fileName, ...(outputFile ? { output_file: outputFile } : {}),
    });
    const completed = result && latestEvent<{ outputs?: string[] }>(result.events, "complete");
    const exported = completed?.outputs?.find((item) => item.toLowerCase().endsWith(`.${evidenceExportFormat}`));
    if (!exported) return;
    if (!isTauri()) {
      try { await downloadWorkspaceFile(exported, fileName); }
      catch (issue) { setError(issue instanceof Error ? issue.message : String(issue)); return; }
    }
    addActivity("Research records exported", fileName, "ok");
  };

  const summarizeEvidenceGeography = async () => {
    if (!workspace || !evidenceRecordsPath) return;
    const result = await execute("workspace-hub", {
      action: "dataset-geography-summary", workspace,
      source_file: evidenceRecordsPath, group_by: geographyGroupBy,
    });
    const summary = result && hubData<GeographySummary>(result.events, "dataset-geography-summary");
    if (summary) setGeographySummary(summary);
  };

  const createEvidenceMap = async () => {
    if (!workspace || !evidenceRecordsPath) return;
    const result = await execute("map", { workspace, source_file: evidenceRecordsPath });
    const complete = result && latestEvent<{ outputs?: string[] }>(result.events, "complete");
    const output = complete?.outputs?.find((item) => item.toLowerCase().endsWith(".html"));
    if (!output) return;
    setEvidenceMapPath(output);
    addActivity("Evidence map created", output.split(/[\\/]/).at(-1) || "Interactive HTML map", "ok");
  };

  const downloadEvidenceMap = async () => {
    if (!evidenceMapPath || isTauri()) return;
    try { await downloadWorkspaceFile(evidenceMapPath, "sugar-evidence-map.html"); }
    catch (issue) { setError(issue instanceof Error ? issue.message : String(issue)); }
  };

  const assignEvidenceGeography = async () => {
    if (!workspace || !evidenceRecordsPath) return;
    const result = await execute("workspace-hub", {
      action: "dataset-geography-assign", workspace, source_file: evidenceRecordsPath,
      row_number: Number(geographyAssignmentRow), country: geographyAssignmentCountry,
      region: geographyAssignmentRegion, city: geographyAssignmentCity, note: geographyAssignmentNote,
    });
    const assigned = result && hubData<Record<string, unknown>>(result.events, "dataset-geography-assign");
    if (assigned) {
      await inspectEvidence();
      await summarizeEvidenceGeography();
      setGeographyAssignmentCountry("");
      setGeographyAssignmentRegion("");
      setGeographyAssignmentCity("");
      setGeographyAssignmentNote("");
    }
  };

  const compareEvidenceGeography = async () => {
    if (!workspace || !evidenceRecordsPath || !geographyComparisonFile.trim()) return;
    const result = await execute("workspace-hub", {
      action: "dataset-region-compare", workspace, source_file: evidenceRecordsPath,
      comparison_file: geographyComparisonFile.trim(), group_by: geographyGroupBy,
    });
    const comparison = result && hubData<GeographyComparison>(result.events, "dataset-region-compare");
    if (comparison) setGeographyComparison(comparison);
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

  const title = PAGE_TITLES[page];
  const navItems = prefs.mode === "advanced" ? [...NAV_BASIC, ...NAV_ADVANCED] : NAV_BASIC;
  const activeRunSummary = overview?.runs.find((r) => ["running", "paused", "queued", "cancelling"].includes(r.status));
  const author = prefs.name.trim() || "Researcher";

  // The project list (project chip, Projects page) and the open project's overview load once the engine is reachable.
  useEffect(() => { void ensureLocalApi().catch(() => undefined).then(() => loadProjects()); }, [loadProjects, apiUrl]);
  useEffect(() => { void refreshOverview(projectId); }, [projectId, refreshOverview]);
  useEffect(() => { if (activeRunSummary && !runId) setRunId(activeRunSummary.run_id); }, [activeRunSummary, runId]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = Boolean(target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)));
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setPaletteOpen((open) => !open); }
      else if (event.key === "?" && !typing && !event.ctrlKey && !event.metaKey) { event.preventDefault(); setHelpOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const commands: Command[] = [
    { id: "go-research", label: "Go to Research", keywords: "new request interpret", run: () => changePage("research") },
    { id: "go-activity", label: "Go to Activity", keywords: "live run progress", run: () => changePage("activity") },
    { id: "go-results", label: "Go to Results", keywords: "items review", run: () => changePage("results") },
    { id: "go-network", label: "Go to Institutions", keywords: "registry sources verify", run: () => changePage("network") },
    { id: "go-map", label: "Go to Map", keywords: "heatmap geography overlap", run: () => changePage("map") },
    { id: "go-projects", label: "Go to Projects", keywords: "switch open", run: () => changePage("projects") },
    { id: "go-settings", label: "Open Settings", keywords: "providers keys credentials preferences", run: () => changePage("settings") },
    { id: "go-about", label: "About SUGAR", keywords: "credits version", run: () => changePage("about") },
    { id: "new-project", label: "New project", keywords: "create", run: () => { changePage("projects"); setCreateSignal((n) => n + 1); } },
    { id: "setup", label: "Run first-time setup", keywords: "onboarding wizard ai model", run: () => setShowSetup(true) },
    { id: "mode", label: prefs.mode === "basic" ? "Switch to Advanced mode" : "Switch to Basic mode", keywords: "experience", run: () => savePrefs({ ...prefs, mode: prefs.mode === "basic" ? "advanced" : "basic" }) },
    { id: "theme", label: prefs.theme === "dark" ? "Use light theme" : "Use dark theme", keywords: "appearance color", run: () => savePrefs({ ...prefs, theme: prefs.theme === "dark" ? "light" : "dark" }) },
    { id: "help", label: "Keyboard shortcuts", hint: "?", keywords: "help keys", run: () => setHelpOpen(true) },
  ];

  const openNewProject = () => { changePage("projects"); setCreateSignal((n) => n + 1); };

  return (
    <div className="app-shell">
      <input ref={evidenceInputRef} className="sr-only" aria-label="Choose evidence records file" type="file" accept=".csv,.jsonl,.ndjson" onChange={(event) => { const file = event.currentTarget.files?.[0]; void uploadEvidenceFile(file); event.currentTarget.value = ""; }} />
      <input ref={datasetInputRef} className="sr-only" aria-label="Choose reference dataset file" type="file" accept=".csv,.tsv,.xlsx,.xls,.json,.jsonl" onChange={(event) => { const file = event.currentTarget.files?.[0]; void uploadRegistryFile(file); event.currentTarget.value = ""; }} />
      <aside className="sidebar">
        <div className="brand-row"><div className="brand-mark">S</div><div><div className="brand-name">SUGAR</div><div className="brand-subtitle">Research workspace</div></div></div>
        <div className="side-caption">RESEARCH</div>
        <nav className="nav-list" aria-label="Main navigation">
          {navItems.map((item) => <button key={item.id} className={`nav-item ${page === item.id ? "active" : ""}`} aria-current={page === item.id ? "page" : undefined} onClick={() => changePage(item.id)}><span className="nav-icon" aria-hidden="true">{item.icon}</span><span className="nav-label">{item.label}</span>{item.id === "activity" && activeRunSummary && <span className="nav-live" title="A run is in progress" />}</button>)}
        </nav>
        <div className="side-caption secondary-caption">PROJECT</div>
        <button className="side-new-project" onClick={openNewProject}><span aria-hidden="true">＋</span> New project</button>
        <button className="project-chip" onClick={() => changePage("projects")} title="Switch project"><span className={`project-indicator ${projectId ? "connected" : ""}`} /><span className="project-chip-copy"><strong>{projectId ? projectName : "No project open"}</strong><small>{projectId ? (overview?.summary.status ? titleCase(overview.summary.status) : "Open") : "Create or choose one"}</small></span><span className="chevron" aria-hidden="true">›</span></button>
        <div className="sidebar-spacer" />
        <div className="engine-card"><div className={`engine-light ${engineState}`} /><div><strong>{engineState === "checking" ? "Connecting to engine" : engineState === "unavailable" ? "Engine unavailable" : engineState === "preview" ? "Browser preview" : isTauri() ? "Local research engine" : "SUGAR API connected"}</strong><small>{engineState === "ready" ? `Python core · ${engineVersion || "connected"}` : engineState === "unavailable" ? "Check the API address and credentials" : engineState === "preview" ? "Connect a research API to work" : "Checking Python core"}</small></div></div>
        <button className={`nav-item settings-link ${page === "settings" ? "active" : ""}`} onClick={() => changePage("settings")} title="Settings"><span className="nav-icon" aria-hidden="true">⚙</span><span className="nav-label">Settings</span></button>
        <button className={`nav-item about-link ${page === "about" ? "active" : ""}`} onClick={() => changePage("about")} title="About SUGAR"><span className="nav-icon" aria-hidden="true">ⓘ</span><span className="nav-label">About</span></button>
        <div className="sidebar-version">SUGAR <span>{engineVersion || "1.4"}</span> · Diplomacy Lab</div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs"><span>SUGAR</span><b>/</b><strong>{title}</strong></div>
          <div className="topbar-actions"><div className={`connection-badge ${busy || activeRunSummary ? "working" : projectId ? "connected" : ""}`}><i />{busy ? "Working…" : activeRunSummary ? "Research running" : projectId ? "Project open" : "No project open"}</div>{overview && <StatusPill status={overview.summary.status} />}<button className="button button-primary button-small" onClick={openNewProject} disabled={Boolean(busy)}><span aria-hidden="true">＋</span> New project</button></div>
        </header>

        {error && <div className="error-banner" role="alert"><span className="error-symbol">!</span><div><strong>Action needs attention</strong><p>{error}</p></div>{/Could not reach|Failed to fetch/i.test(error) && <button className="button button-secondary button-small" onClick={() => { setError(""); changePage("settings"); }}>Connection settings</button>}<button onClick={() => setError("")} aria-label="Dismiss error">×</button></div>}
        {busy && <div className="progress-line"><i /></div>}

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
            <div className="panel project-profile-panel"><div className="section-title"><div className="section-icon amber">✎</div><div><h3>Project notes and members</h3><p>Keep shared context and a local member roster with this project.</p></div></div><label className="field-block"><span>Project notes</span><textarea aria-label="Project context notes" value={projectContextNotes} onChange={(event) => setProjectContextNotes(event.target.value)} rows={3} placeholder="Purpose, constraints, source policy, or handoff context" /></label><div className="project-member-list" role="group" aria-label="Project member roster">{projectMembers.map((member, index) => <div className="project-member-row" key={index}><label className="field-block"><span>Name</span><input aria-label={`Member ${index + 1} name`} value={member.name} onChange={(event) => updateProjectMember(index, "name", event.target.value)} /></label><label className="field-block"><span>Email</span><input aria-label={`Member ${index + 1} email`} type="email" value={member.email} onChange={(event) => updateProjectMember(index, "email", event.target.value)} /></label><label className="field-block"><span>Access role</span><select aria-label={`Member ${index + 1} role`} value={["owner", "analyst", "reviewer", "viewer"].includes(member.role.toLowerCase()) ? member.role.toLowerCase() : member.role.toLowerCase().includes("lead") ? "analyst" : "viewer"} onChange={(event) => updateProjectMember(index, "role", event.target.value)}><option value="owner">Owner</option><option value="analyst">Analyst</option><option value="reviewer">Reviewer</option><option value="viewer">Viewer</option></select></label><button className="button button-quiet" type="button" aria-label={`Remove member ${index + 1}`} onClick={() => setProjectMembers((members) => members.filter((_, current) => current !== index))}>Remove</button>{!isTauri() && <div className="member-access-actions"><button className="button button-secondary button-small" type="button" onClick={() => void issueProjectMemberAccess(member.email)} disabled={!member.email.trim()}>Issue access</button><button className="button button-quiet button-small" type="button" onClick={() => void revokeProjectMemberAccess(member.email)} disabled={!member.email.trim()}>Revoke access</button></div>}</div>)}</div><div className="project-profile-actions"><button className="button button-quiet" type="button" onClick={addProjectMember} disabled={Boolean(busy)}>＋ Add member</button><button className="button button-primary" type="button" onClick={() => void saveProjectProfile()} disabled={!workspace || Boolean(busy)}>Save project profile</button></div>{memberAccessMessage && <div className="member-access-message" role="status" aria-live="polite"><p>{memberAccessMessage}</p>{memberAccessToken && <label className="field-block"><span>One-time member token</span><input aria-label="One-time member access token" type="password" autoComplete="off" readOnly value={memberAccessToken} onFocus={(event) => event.currentTarget.select()} /></label>}</div>}<p className="muted-copy">Authenticated members receive project-scoped roles enforced by the connected SUGAR API. Local desktop projects use the device account.</p></div>
            <div className="panel listening-post-panel"><div className="section-title"><div className="section-icon green">◉</div><div><h3>Recurring listening posts</h3><p>Scheduled search definitions persist here and run through the same source collectors.</p></div></div><div className="monitor-create-grid"><label className="field-block"><span>Listening post name</span><input aria-label="Listening post name" value={monitorName} onChange={(event) => setMonitorName(event.target.value)} placeholder="e.g. Weekly service updates" /></label><label className="field-block"><span>Search sources</span><input aria-label="Listening post sources" value={monitorSources} onChange={(event) => setMonitorSources(event.target.value)} placeholder="x, bluesky" /></label><label className="field-block"><span>Cadence in minutes</span><input aria-label="Listening post cadence" type="number" min="5" max="525600" step="1" value={monitorCadence} onChange={(event) => setMonitorCadence(event.target.value)} /></label><label className="field-block"><span>Geographies</span><input aria-label="Listening post geographies" value={monitorGeographies} onChange={(event) => setMonitorGeographies(event.target.value)} placeholder="Optional" /></label><label className="field-block monitor-query-field"><span>Search terms <small>One query per line</small></span><textarea aria-label="Listening post search terms" rows={3} value={monitorTerms} onChange={(event) => setMonitorTerms(event.target.value)} /></label></div><div className="monitor-actions"><button className="button button-primary" type="button" onClick={() => void saveListeningMonitor()} disabled={!monitorName.trim() || !monitorTerms.trim() || Boolean(busy)}>Save listening post</button><button className="button button-secondary" type="button" onClick={() => void loadListeningMonitors()} disabled={!workspace || Boolean(busy)}>Refresh schedule</button><button className="button button-secondary" type="button" onClick={() => void runDueListeningMonitors()} disabled={!workspace || Boolean(busy)}>Run due checks now</button></div><div className="monitor-list">{listeningMonitors.length ? listeningMonitors.map((monitor) => <article className="monitor-row" key={monitor.monitor_id}><div><strong>{monitor.name}</strong><span>{monitor.status} · every {monitor.cadence_minutes} minutes · next due {monitor.next_due_at || "when scheduled"}</span><small>{(monitor.sources || []).join(", ")} · {(monitor.terms || []).join(" / ")}</small></div><button className="button button-quiet" type="button" onClick={() => void setListeningMonitorStatus(monitor)} disabled={Boolean(busy)}>{monitor.status === "active" ? "Pause" : "Resume"}</button></article>) : <p className="muted-copy">No listening posts are saved for this project.</p>}</div><p className="muted-copy">The app does not run a hidden scheduler. To collect automatically, configure your operating-system scheduler to invoke <code>{isTauri() ? `sugar-project monitor-run-due "${workspace}"` : "sugar-project monitor-run-due <server project path>"}</code> at your preferred check interval. Hosted projects require the API server operator to configure that job.</p></div>
            <div className="panel project-comments-panel"><div className="section-title"><div className="section-icon blue">☷</div><div><h3>Project discussion</h3><p>Append-only comments are shared with people who have access to this project.</p></div><button className="button button-quiet" type="button" onClick={() => void loadProjectComments()} disabled={!workspace || Boolean(busy)}>Refresh</button></div><div className="project-comment-list" role="log" aria-label="Project comments" aria-live="polite">{projectComments.length ? projectComments.map((comment) => <article className="project-comment" key={comment.comment_id}><div><strong>{comment.actor}</strong><time dateTime={comment.created_at}>{new Date(comment.created_at).toLocaleString()}</time></div><p>{comment.body}</p></article>) : <p className="muted-copy">No comments have been added to this project.</p>}</div><div className="project-comment-compose"><label className="field-block"><span>Displayed name</span><input aria-label="Comment author name" value={commentAuthor} onChange={(event) => setCommentAuthor(event.target.value)} /></label><label className="field-block"><span>Comment</span><textarea aria-label="Project comment" value={commentDraft} onChange={(event) => setCommentDraft(event.target.value)} rows={3} maxLength={10000} placeholder="Add a project update or question" /></label><button className="button button-primary" type="button" onClick={() => void addProjectComment()} disabled={!workspace || !commentDraft.trim() || Boolean(busy)}>Add comment</button></div></div>
            <div className="panel requirement-panel"><div className="section-title"><div className="section-icon violet">⌕</div><div><h3>Research requirement</h3><p>A precise question gives the search plan a useful starting point.</p></div><span className="step-badge">STEP 1</span></div><div className="research-template-toolbar"><label className="field-block"><span>Research requirement template</span><select aria-label="Research requirement template" value={selectedResearchTemplate} onChange={(event) => setSelectedResearchTemplate(event.target.value)}><option value="">Choose a saved or starter template</option>{researchTemplates.map((template) => <option key={template.template_id} value={template.template_id}>{template.name}</option>)}</select></label><div className="research-template-actions"><button className="button button-quiet" type="button" onClick={() => void loadResearchTemplates()} disabled={!workspace || Boolean(busy)}>Load templates</button><button className="button button-secondary" type="button" onClick={applyResearchTemplate} disabled={!selectedResearchTemplate}>Use template</button></div><label className="field-block"><span>Save current requirement as a template</span><input aria-label="New research template name" value={researchTemplateName} onChange={(event) => setResearchTemplateName(event.target.value)} placeholder="e.g. Annual regional scan" /></label><button className="button button-quiet" type="button" onClick={() => void saveResearchTemplate()} disabled={!workspace || !researchTemplateName.trim() || Boolean(busy)}>Save template</button></div><form className="research-form" onSubmit={(event) => void createRequirement(event)}><label className="field-block"><span>Research question <em>Required</em></span><textarea value={question} onChange={(event) => setQuestion(event.target.value)} required rows={3} placeholder="What would you like to understand?" /></label><label className="field-block"><span>Project notes</span><textarea aria-label="Project notes" value={projectNotes} onChange={(event) => setProjectNotes(event.target.value)} rows={2} placeholder="Context, constraints, or analyst notes to keep with this requirement" /></label><div className="field-grid"><label className="field-block"><span>Geographies</span><input value={geography} onChange={(event) => setGeography(event.target.value)} placeholder="Countries, regions, or cities" /><small>Separate multiple places with commas.</small></label><label className="field-block"><span>Known institutions or entities</span><input value={knownEntities} onChange={(event) => setKnownEntities(event.target.value)} placeholder="Names already in scope" /><small>Optional starting points for the plan.</small></label></div><label className="field-block"><span>Intended audience</span><input value={audience} onChange={(event) => setAudience(event.target.value)} placeholder="Who will use the results?" /></label><div className="field-grid"><label className="field-block"><span>Start date</span><input aria-label="Start date" type="date" value={timeframeStart} onChange={(event) => setTimeframeStart(event.target.value)} /></label><label className="field-block"><span>End date</span><input aria-label="End date" type="date" value={timeframeEnd} onChange={(event) => setTimeframeEnd(event.target.value)} /></label></div><div className="field-grid"><label className="field-block"><span>Languages</span><input aria-label="Languages" value={languages} onChange={(event) => setLanguages(event.target.value)} placeholder="auto or language codes, e.g. es, zh" /><small>Use language codes separated by commas; auto leaves filtering open.</small></label><label className="field-block"><span>Collection sources</span><input aria-label="Collection sources" value={preferredSources} onChange={(event) => setPreferredSources(event.target.value)} placeholder="x, bluesky, mastodon, weibo, bilibili" /><small>Use x or bluesky for keyword search. Mastodon needs a token for keywords; without one, use a #hashtag query. Weibo and Bilibili keyword search may require provider access.</small></label></div><label className="field-block"><span>Excluded topics</span><input aria-label="Excluded topics" value={excludedTopics} onChange={(event) => setExcludedTopics(event.target.value)} placeholder="Topics to leave out of the search plan" /><small>Separate exclusions with commas.</small></label><label className="check-field"><input aria-label="Translate collected posts" type="checkbox" checked={translatePosts} onChange={(event) => setTranslatePosts(event.target.checked)} /><span>Translate collected posts to English during collection<small>Uses the provider key in Settings; originals remain available.</small></span></label><label className="check-field"><input aria-label="Infer broad locations for mapping" type="checkbox" checked={inferLocations} onChange={(event) => setInferLocations(event.target.checked)} /><span>Infer broad locations for mapping<small>Uses the provider key and geocodes only supported public place evidence; records without a supported location remain unmapped.</small></span></label><div className="form-footer"><span className="privacy-note"><span>◉</span> The requirement is saved in this project folder.</span><button className="button button-primary" type="submit" disabled={!workspace || !question.trim() || Boolean(busy)}>Save research requirement <span>→</span></button></div></form></div>
            <div className="panel public-item-panel"><div className="section-title"><div className="section-icon green">↗</div><div><h3>Collect a public item by URL</h3><p>Use a known public Weibo post, Bilibili video, or WeChat article when keyword search is restricted.</p></div></div><div className="field-grid"><label className="field-block"><span>Source</span><select aria-label="Public item source" value={publicItemSource} onChange={(event) => setPublicItemSource(event.target.value)}><option value="weibo">Weibo post</option><option value="bilibili">Bilibili video</option><option value="wechat">WeChat article</option></select></label><label className="field-block"><span>Public URL</span><input aria-label="Public item URL" type="url" value={publicItemUrl} onChange={(event) => setPublicItemUrl(event.target.value)} placeholder="https://…" /></label></div><button className="button button-secondary" type="button" onClick={() => void importPublicItem()} disabled={!workspace || !publicItemUrl.trim() || Boolean(busy)}>Collect public item</button><p className="muted-copy">A collected item becomes the selected evidence dataset for inspection and coding. Provider access rules still apply.</p></div>
            <div className="panel public-hashtag-panel"><div className="section-title"><div className="section-icon green">#</div><div><h3>Collect a public Mastodon hashtag</h3><p>Collect public posts from mastodon.social without a search token. This searches one hashtag, not all text across the network.</p></div></div><div className="field-grid"><label className="field-block"><span>Hashtag</span><input aria-label="Mastodon public hashtag" value={mastodonHashtag} onChange={(event) => setMastodonHashtag(event.target.value)} placeholder="#education" /></label><button className="button button-secondary" type="button" onClick={() => void collectPublicHashtag()} disabled={!workspace || !mastodonHashtag.trim() || Boolean(busy)}>Collect hashtag</button></div></div>
            <div className="panel evidence-panel"><div className="section-title"><div className="section-icon blue">▤</div><div><h3>Import and inspect research records</h3><p>Bring in an authorized CSV or JSONL dataset and inspect its source fields.</p></div><span className="step-badge">STEP 2</span></div><div className="evidence-import-row"><div className="evidence-file"><span className="file-mark">▧</span><div><strong>{evidenceFile ? evidenceFile.split(/[\\/]/).at(-1) : evidenceRecordsPath ? "Research records are in this project" : "No evidence dataset selected"}</strong><small>{evidenceRecordsPath || "Choose a CSV or JSONL file to begin an auditable import."}</small></div></div><div className="evidence-actions"><button className="button button-secondary" onClick={() => void chooseEvidenceFile()} disabled={!workspace || Boolean(busy)}>Choose data</button>{evidenceFile && <button className="button button-primary" onClick={() => void importEvidence()} disabled={Boolean(busy)}>Import records <span>→</span></button>}</div></div>{evidenceRecordsPath && <div className="evidence-review-row"><span className={`review-state ${reviewPrepared ? "ready" : "pending"}`}><i />{reviewPrepared ? "Human-review draft prepared" : "Evidence selected · awaiting review draft"}</span><div className="evidence-actions"><button className="button button-quiet" onClick={() => void inspectEvidence()} disabled={Boolean(busy)}>Inspect records</button><button className="button button-secondary" onClick={() => void prepareEvidenceReview()} disabled={reviewPrepared || Boolean(busy)}>{reviewPrepared ? "Review draft ready" : "Prepare human review"}</button><button className="button button-secondary" onClick={() => void codeEvidence()} disabled={Boolean(busy)} title="Uses the default provider configured in Settings">Generate coded findings</button><label className="field-block export-format-select"><span>Export as</span><select aria-label="Evidence export format" value={evidenceExportFormat} onChange={(event) => setEvidenceExportFormat(event.target.value)}><option value="csv">CSV</option><option value="xlsx">Excel</option><option value="jsonl">JSON Lines</option><option value="json">JSON</option><option value="geojson">GeoJSON</option></select></label><label className="field-block geography-group-select"><span>Geographic grouping</span><select aria-label="Geographic grouping" value={geographyGroupBy} onChange={(event) => setGeographyGroupBy(event.target.value)}><option value="auto">Automatic hierarchy</option><option value="country">Country</option><option value="region">Region</option><option value="city">City</option><option value="coordinate_grid">Coordinate cells</option></select></label><button className="button button-secondary" onClick={() => void summarizeEvidenceGeography()} disabled={Boolean(busy)}>Summarize geography</button><button className="button button-secondary" onClick={() => void createEvidenceMap()} disabled={Boolean(busy)}>Create evidence map</button><button className="button button-quiet" onClick={() => void exportEvidence()} disabled={Boolean(busy)}>Export data</button></div></div>}{evidenceMapPath && <div className="evidence-map-result" role="status"><strong>Interactive evidence map ready</strong><span>{evidenceMapPath}</span>{!isTauri() && <button className="button button-secondary" type="button" onClick={() => void downloadEvidenceMap()}>Download map</button>}</div>}{evidencePreview && <div className="evidence-preview"><div className="preview-summary"><strong>{evidencePreview.row_count ?? 0} source records</strong><span>Showing {evidencePreview.rows?.length || 0} · source text and URL retained</span></div><div className="evidence-table-scroll"><table className="evidence-table"><thead><tr>{(evidencePreview.columns || []).filter((column) => ["platform", "author_name", "content_type", "original_text", "canonical_url", "source_url", "published_at", "query"].includes(column)).slice(0, 6).map((column) => <th key={column}>{titleCase(column)}</th>)}</tr></thead><tbody>{(evidencePreview.rows || []).map((row, index) => <tr key={String(row.record_key || row.native_id || index)}>{(evidencePreview.columns || []).filter((column) => ["platform", "author_name", "content_type", "original_text", "canonical_url", "source_url", "published_at", "query"].includes(column)).slice(0, 6).map((column) => <td key={column} title={String(row[column] ?? "")}>{String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table></div></div>}{geographySummary && <section className="geography-summary" aria-label="Geographic summary"><div className="preview-summary"><strong>Geographic groups · {geographySummary.total_rows || 0} records</strong><span>{geographySummary.located_rows || 0} located · {geographySummary.unlocated_rows || 0} unlocated · {titleCase(geographySummary.group_by || "auto")}</span></div><div className="geography-summary-list">{(geographySummary.groups || []).slice(0, 12).map((group) => <div key={String(group.label)}><span>{String(group.label || "Unspecified")}</span><strong>{group.records || 0}</strong></div>)}</div><p className="muted-copy">{geographySummary.guardrail}</p></section>}<section className="geography-review-tools" aria-label="Geographic review">
              {evidencePreview && <div className="manual-geography-panel"><div><strong>Analyst-assigned geography</strong><p>Assignments are kept as separate annotations; source fields are preserved. Edits are tied to this exact file version.</p></div><label className="field-block"><span>Dataset row</span><select aria-label="Geography assignment record" value={geographyAssignmentRow} onChange={(event) => setGeographyAssignmentRow(event.target.value)}>{(evidencePreview.rows || []).map((row, index) => { const rowNumber = Number(row._sugar_row_number ?? index); return <option key={rowNumber} value={rowNumber}>Row {rowNumber + 1} · {String(row.record_id || row.record_key || row.native_id || row.original_text || `record ${rowNumber + 1}`).slice(0, 80)}</option>; })}</select></label><div className="field-grid"><label className="field-block"><span>Country</span><input aria-label="Assigned country" value={geographyAssignmentCountry} onChange={(event) => setGeographyAssignmentCountry(event.target.value)} /></label><label className="field-block"><span>Region</span><input aria-label="Assigned region" value={geographyAssignmentRegion} onChange={(event) => setGeographyAssignmentRegion(event.target.value)} /></label><label className="field-block"><span>City</span><input aria-label="Assigned city" value={geographyAssignmentCity} onChange={(event) => setGeographyAssignmentCity(event.target.value)} /></label></div><label className="field-block"><span>Assignment note</span><input aria-label="Geography assignment note" value={geographyAssignmentNote} onChange={(event) => setGeographyAssignmentNote(event.target.value)} placeholder="Evidence or rationale for this location" /></label><button className="button button-secondary" type="button" onClick={() => void assignEvidenceGeography()} disabled={!evidenceRecordsPath || ![geographyAssignmentCountry, geographyAssignmentRegion, geographyAssignmentCity].some((value) => value.trim()) || Boolean(busy)}>Save analyst assignment</button></div>}
              <div className="region-comparison-panel"><div><strong>Compare two geographic distributions</strong><p>Uses the selected grouping and any current analyst annotations.</p></div><label className="field-block"><span>Comparison dataset path</span><input aria-label="Comparison dataset path" value={geographyComparisonFile} onChange={(event) => setGeographyComparisonFile(event.target.value)} placeholder="Project file path or sugar-file reference" /></label><button className="button button-secondary" type="button" onClick={() => void compareEvidenceGeography()} disabled={!evidenceRecordsPath || !geographyComparisonFile.trim() || Boolean(busy)}>Compare regions</button>{geographyComparison && <><div className="preview-summary"><strong>{geographyComparison.left_total || 0} baseline · {geographyComparison.right_total || 0} comparison records</strong><span>{titleCase(geographyComparison.group_by || geographyGroupBy)}</span></div><div className="evidence-table-scroll"><table className="evidence-table"><thead><tr><th>Geographic group</th><th>Baseline</th><th>Comparison</th><th>Share difference</th></tr></thead><tbody>{(geographyComparison.groups || []).map((group) => <tr key={String(group.label)}><td>{String(group.label || "Unspecified")}</td><td>{group.left_records || 0} · {((group.left_share || 0) * 100).toFixed(1)}%</td><td>{group.right_records || 0} · {((group.right_share || 0) * 100).toFixed(1)}%</td><td>{((group.share_difference || 0) * 100).toFixed(1)} pp</td></tr>)}</tbody></table></div><p className="muted-copy">{geographyComparison.guardrail}</p></>}</div>
            </section></div>
            {codedFindingsPreview && <div className="panel coded-findings-panel"><div className="section-title"><div className="section-icon violet">✦</div><div><h3>AI-coded findings</h3><p>{codedFindingsPreview.row_count ?? 0} proposed codes · {codedFindingsPath.split(/[\\/]/).at(-1) || "triage output"}</p></div><span className="review-state pending"><i />Human review required</span></div><p className="coded-findings-note">These are model-assisted classifications for analyst review. They are not verified findings or evidence of intent.</p><div className="evidence-table-scroll"><table className="evidence-table"><thead><tr>{(codedFindingsPreview.columns || []).filter((column) => ["observation_type", "summary", "country", "city", "triage_labels", "ai_confidence", "verification_state"].includes(column)).slice(0, 7).map((column) => <th key={column}>{titleCase(column)}</th>)}</tr></thead><tbody>{(codedFindingsPreview.rows || []).map((row, index) => <tr key={String(row.observation_id || index)}>{(codedFindingsPreview.columns || []).filter((column) => ["observation_type", "summary", "country", "city", "triage_labels", "ai_confidence", "verification_state"].includes(column)).slice(0, 7).map((column) => <td key={column} title={String(row[column] ?? "")}>{Array.isArray(row[column]) ? row[column].join(", ") : String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table></div></div>}
            <div className="panel plan-panel"><div className="section-title"><div className="section-icon green">☷</div><div><h3>Search plan</h3><p>Generate a deterministic first plan for review before any collection.</p></div><span className="step-badge">STEP 3</span></div>{strategy && <div className="strategy-review-card"><div><strong>AI interpretation · {String(strategy.review_state || "draft")}</strong><p>Explicit phrases, semantic interpretation, and hypotheses stay separate. Review before this strategy shapes a plan.</p></div><ul>{(Array.isArray(strategy.concepts) ? strategy.concepts as Array<Record<string, unknown>> : []).slice(0, 8).map((concept, index) => <li key={String(concept.concept_id || index)}><span>{titleCase(String(concept.origin || "interpreted"))} · {titleCase(String(concept.kind || "concept"))}</span><strong>{String(concept.value || "")}</strong></li>)}</ul>{String(strategy.review_state || "draft") === "draft" && <button className="button button-secondary" onClick={() => void approveInterpretation()} disabled={Boolean(busy)}>Approve interpretation</button>}</div>}<div className="plan-callout"><div className="plan-callout-copy"><strong>{plan ? "Plan ready to inspect" : "Plan only runs after the requirement is saved"}</strong><span>{plan ? `${Array.isArray(plan.branches) ? plan.branches.length : 0} search branches · no provider key required` : "You stay in control of what gets collected."}</span></div><button className="button button-secondary" onClick={() => void interpretRequirement()} disabled={!workspace || !requirementSaved || !credentials.llm_api_key?.trim() || Boolean(busy)} title={!credentials.llm_api_key?.trim() ? "Add a provider key in Settings first" : "Interpret this requirement with strict structured output"}>{strategy ? "Reinterpret with AI" : "Interpret with AI"}</button><button className="button button-secondary" onClick={() => void buildPlan()} disabled={!workspace || !requirementSaved || Boolean(busy) || Boolean(strategy && String(strategy.review_state || "draft") !== "approved")}>{plan ? "Refresh plan" : "Build research plan"} <span>→</span></button></div>{plan && <><div className="plan-preview">{Array.isArray(plan.branches) && plan.branches.length ? plan.branches.slice(0, 6).map((branch, index) => { const row = branch as Record<string, unknown>; return <div className="plan-branch" key={String(row.branch_id || index)}><span className="branch-number">{String(index + 1).padStart(2, "0")}</span><div><strong>{String(row.query || "Search branch")}</strong><p>{String(row.rationale || row.origin || "Review this line of inquiry before collection.")}</p></div><span className="branch-status">{titleCase(String(row.status || "proposed"))}</span></div>; }) : <p className="muted-copy">{String(plan.message || "Research plan generated.")}</p>}</div><details className="platform-tuning-panel"><summary>Per-platform collection limits</summary><p>Leave a field blank to use the plan-wide limit. Source caps never exceed the run-wide budget.</p><div className="platform-tuning-grid">{COLLECTION_SOURCES.map((source) => <div className="platform-tuning-row" key={source}><strong>{titleCase(source)}</strong><label className="field-block"><span>Posts per query</span><input aria-label={`${titleCase(source)} maximum posts per query`} type="number" min="1" max="1000" step="1" value={platformTuning[source]?.max_posts_per_query || ""} onChange={(event) => setPlatformTuning((current) => ({ ...current, [source]: { max_posts_per_query: event.target.value, max_pages_per_query: current[source]?.max_pages_per_query || "" } }))} /></label><label className="field-block"><span>Pages per query</span><input aria-label={`${titleCase(source)} maximum pages per query`} type="number" min="1" max="100" step="1" value={platformTuning[source]?.max_pages_per_query || ""} onChange={(event) => setPlatformTuning((current) => ({ ...current, [source]: { max_posts_per_query: current[source]?.max_posts_per_query || "", max_pages_per_query: event.target.value } }))} /></label></div>)}</div></details><div className="collection-footer"><span>Review the plan above, then start collection when ready.</span><button className="button button-primary" onClick={() => void startLiveCollection()} disabled={!commaList(preferredSources).length || Boolean(busy)}>Run plan collection <span>→</span></button></div>
            {activeCollectionRunId && <section className="collection-live-controls" aria-labelledby="collection-controls-title"><div className="collection-live-heading"><div><h4 id="collection-controls-title">Live collection controls</h4><p>Updates take effect between source requests. A request already in progress will finish first.</p></div><span className="run-live-badge">Run active</span></div><div className="collection-live-grid"><label className="field-block"><span>Search queries <small>One query per line</small></span><textarea aria-label="Live search queries" rows={4} value={collectionScope.terms} onChange={(event) => setCollectionScope((current) => ({ ...current, terms: event.target.value }))} /></label><div className="collection-live-fields"><label className="field-block"><span>Active sources <small>Comma-separated; remove a source to disable it</small></span><input aria-label="Live collection sources" value={collectionScope.sources} onChange={(event) => setCollectionScope((current) => ({ ...current, sources: event.target.value }))} /></label><label className="field-block"><span>Excluded topics</span><input aria-label="Live excluded topics" value={collectionScope.excluded_topics} onChange={(event) => setCollectionScope((current) => ({ ...current, excluded_topics: event.target.value }))} /></label><label className="field-block"><span>Post languages</span><input aria-label="Live post languages" value={collectionScope.post_languages} onChange={(event) => setCollectionScope((current) => ({ ...current, post_languages: event.target.value }))} placeholder="Blank means any language" /></label><div className="field-grid"><label className="field-block"><span>From date</span><input aria-label="Live start date" type="date" value={collectionScope.since} onChange={(event) => setCollectionScope((current) => ({ ...current, since: event.target.value }))} /></label><label className="field-block"><span>Through date</span><input aria-label="Live end date" type="date" value={collectionScope.until} onChange={(event) => setCollectionScope((current) => ({ ...current, until: event.target.value }))} /></label></div></div></div><div className="collection-live-actions"><label className="field-block"><span>Retry source</span><select aria-label="Source to retry" value={collectionRetrySource} onChange={(event) => setCollectionRetrySource(event.target.value)}>{COLLECTION_SOURCES.map((source) => <option key={source} value={source}>{titleCase(source)}</option>)}</select></label><button type="button" className="button button-secondary" onClick={() => void sendCollectionControl()} disabled={collectionControlBusy}>Apply changes</button><button type="button" className="button button-secondary" onClick={() => void sendCollectionControl({ retry_source: collectionRetrySource })} disabled={collectionControlBusy}>Retry source</button><button type="button" className="button button-quiet" onClick={() => void sendCollectionControl({ cancel: true })} disabled={collectionControlBusy}>Stop after current request</button></div><p className="collection-live-status" role="status" aria-live="polite">{collectionControlMessage}</p></section>}</>}</div>
          </div><aside className="column-side"><div className="side-note"><div className="note-mark">✧</div><span className="eyebrow">RESEARCH PRACTICE</span><h3>Keep the question visible.</h3><p>Every dataset, search, and analysis should trace back to a documented requirement. You can update it as the work evolves.</p><div className="note-separator" /><div className="note-stat"><strong>{requirementSaved ? "Saved" : "Not started"}</strong><span>Requirement status</span></div><div className="note-stat"><strong>{plan ? "Ready" : "Waiting"}</strong><span>Search plan status</span></div></div><div className="help-card"><span className="help-icon">i</span><div><strong>Review before collection</strong><p>The plan is a working proposal. Inspect its search branches before starting a collector run.</p></div></div></aside></div>
        </section>}

        {page === "institutions" && <section className="page-content institutions-page">
          <div className="page-heading compact-heading"><div><div className="eyebrow">REFERENCE REGISTRY <span className="eyebrow-line" /></div><h1>Institutions, on the map.</h1><p>Inspect locations, status, and sources from this project’s registry.</p></div><div className="heading-actions"><button className="button button-secondary" onClick={() => void importFile()} disabled={!workspace || Boolean(busy)}><span>＋</span> Import dataset</button><button className="button button-primary" onClick={() => void refreshRegistry()} disabled={!workspace || Boolean(busy)}><span>↻</span> Refresh registry</button></div></div>
          {preview && <div className="import-banner"><div className="import-intro"><div className="section-icon violet">⇧</div><div><strong>Review field mapping before import</strong><p>{datasetFileLabel || datasetFile.split(/[\\/]/).at(-1)} · {preview.row_count ?? "?"} source rows</p></div></div><div className="import-fields"><label className="field-block"><span>Dataset name</span><input value={datasetName} onChange={(event) => setDatasetName(event.target.value)} /></label><label className="field-block"><span>Institution network</span><input value={datasetNetwork} onChange={(event) => setDatasetNetwork(event.target.value)} placeholder="e.g. American Spaces" /></label></div><label className="field-block mapping-field"><span>Canonical field → source column <small>Adjust the suggested mapping where needed.</small></span><textarea className="mapping-text" value={mappingText} onChange={(event) => setMappingText(event.target.value)} rows={5} spellCheck={false} /></label><div className="import-footer"><span>Source: {preview.columns?.join(" · ") || "Detected columns"}</span><div><button className="button button-quiet" onClick={() => setPreview(null)}>Cancel</button><button className="button button-primary" onClick={() => void commitImport()} disabled={Boolean(busy)}>Import mapped records <span>→</span></button></div></div></div>}
          {datasetFile && !preview && <div className="pending-import"><span><strong>Dataset selected</strong> · {datasetFileLabel || datasetFile.split(/[\\/]/).at(-1)}</span><div><button className="button button-quiet" onClick={() => { setDatasetFile(""); setDatasetFileLabel(""); }}>Cancel</button><button className="button button-primary" onClick={() => void previewImport()} disabled={Boolean(busy)}>Preview field mapping <span>→</span></button></div></div>}
          <div className="registry-toolbar"><div className="search-field"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search institution, place, or network" /></div><label className="select-wrap"><span className="sr-only">Filter by network</span><select value={network} onChange={(event) => setNetwork(event.target.value)}>{networks.map((item) => <option key={item}>{item}</option>)}</select><b>⌄</b></label><label className="select-wrap"><span className="sr-only">Filter by status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>{["All statuses", "active", "closed", "proposed", "unknown"].map((item) => <option key={item}>{item}</option>)}</select><b>⌄</b></label><span className="registry-total"><strong>{filteredRows.length}</strong> of {registry.length}</span></div>
          <div className="registry-workspace"><div className="map-column"><div className="map-heading"><div><strong>Institution map</strong><span>Status layers · drag a point to propose a location change for analyst review</span></div><div className="map-tools"><span className="map-data-tag"><i /> {locatedCount} mapped</span></div></div>{workspace ? <InstitutionMap rows={filteredRows} onSelect={(id) => setSelected(registry.find((row) => row.entity_id === id) || null)} onMove={(id, latitude, longitude) => void moveInstitution(id, latitude, longitude)} /> : <div className="map-empty"><span>⌖</span><strong>Open a project to view its registry map</strong><p>Institution locations will appear here when registry records are available.</p><button className="button button-primary" onClick={() => void chooseWorkspace()}>Open project</button></div>}</div><aside className="registry-side"><div className="registry-list-heading"><div><strong>Registry records</strong><span>{filteredRows.length} visible records</span></div><button className="icon-button" title="Refresh" onClick={() => void refreshRegistry()} disabled={!workspace || Boolean(busy)}>↻</button></div><div className="registry-list">{filteredRows.length ? filteredRows.slice(0, 300).map((row) => <button className={`registry-row ${selected?.entity_id === row.entity_id ? "selected" : ""}`} key={row.entity_id} onClick={() => setSelected(row)}><span className="institution-avatar">{(row.name || "?").slice(0, 1).toUpperCase()}</span><span className="institution-copy"><strong>{row.name || "Unnamed institution"}</strong><span>{[row.city, row.country].filter(Boolean).join(", ") || row.network || "Place not specified"}</span><small>{row.network || titleCase(row.entity_type || "Institution")}</small></span><span className={`status-dot status-${String(row.status || "unknown").toLowerCase()}`} /></button>) : <div className="list-empty"><span>⌖</span><strong>{registry.length ? "No matching institutions" : "No registry loaded"}</strong><p>{registry.length ? "Try a broader search or filter." : "Refresh the registry or import a reference dataset."}</p>{!registry.length && <button className="text-button" onClick={() => void refreshRegistry()} disabled={!workspace || Boolean(busy)}>Load registry →</button>}</div>}</div></aside></div>
          {selected && <div className="inspector-backdrop" onClick={() => setSelected(null)}><aside className="evidence-inspector" onClick={(event) => event.stopPropagation()}><div className="inspector-top"><div><span className="eyebrow">INSTITUTION RECORD</span><button className="inspector-close" onClick={() => setSelected(null)} aria-label="Close inspector">×</button></div><div className="inspector-identity"><div className="inspector-avatar">{(selected.name || "?").slice(0, 1).toUpperCase()}</div><div><h2>{selected.name || "Unnamed institution"}</h2><span>{[selected.city, selected.country].filter(Boolean).join(", ") || "Location not recorded"}</span></div></div><div className="inspector-badges"><span className={`status-pill status-pill-${String(selected.status || "unknown").toLowerCase()}`}>{titleCase(selected.status || "unknown")}</span><span className="network-pill">{selected.network || titleCase(selected.entity_type || "Institution")}</span></div></div><div className="inspector-content"><div className="inspector-section"><span className="eyebrow">PROFILE</span><p>{selected.description || "No descriptive profile has been recorded for this institution."}</p><div className="profile-facts"><div><span>Entity type</span><strong>{titleCase(selected.entity_type || "institution")}</strong></div><div><span>Coordinates</span><strong>{coordinatesText(selected)}</strong></div><div><span>Registry ID</span><strong>{selected.entity_id}</strong></div></div></div><div className="inspector-section"><div className="evidence-heading"><span className="eyebrow">EVIDENCE & SOURCES</span><span className="source-count">{extractEvidence(selected).length}</span></div>{extractEvidence(selected).length ? <div className="source-list">{extractEvidence(selected).map((source) => <a className="source-link" key={source.url} href={source.url} target="_blank" rel="noreferrer"><span className="source-icon">↗</span><span><strong>{source.label}</strong><small>{new URL(source.url).hostname}</small></span></a>)}</div> : <div className="evidence-gap"><span>◷</span><div><strong>Evidence gap</strong><p>No source URL has been attached yet. Verify this record before relying on its status or location.</p></div></div>}</div></div><div className="inspector-footer"><span>Claim-level source provenance is retained in the project registry.</span></div></aside></div>}
        </section>}

        {page === "research" && <ResearchPage prefill={prefill} projectId={projectId} projectName={projectName} prefs={prefs} overview={overview} onOverview={() => refreshOverview(projectId)} ensureProject={ensureProject} onRunStarted={handleRunStarted} onOpenSettings={() => changePage("settings")} onOpenResults={(id) => { setRunId(id); changePage("results"); }} onError={setError} />}
        {page === "activity" && <ActivityView onRunSettled={(finished) => { void refreshOverview(projectId); const kept = finished.counts?.processed ?? finished.counts?.collected ?? 0; if (finished.status === "failed") notify("The run could not finish. Open Activity for details.", "warn"); else if (finished.status === "cancelled") notify(`Run cancelled — ${kept} items kept.`, "info"); else notify(`Run finished — ${kept} item${kept === 1 ? "" : "s"} kept${finished.status === "completed_with_warnings" ? ", with some sources incomplete" : ""}.`, finished.status === "completed" ? "ok" : "warn", { label: "View results", run: () => changePage("results") }); }} projectId={projectId} runId={runId} prefs={prefs} author={author} onOpenResults={(id) => { setRunId(id); changePage("results"); }} onNewRun={() => changePage("research")} onOpenSettings={() => changePage("settings")} onRunStarted={handleRunStarted} onError={setError} />}
        {page === "results" && <ResultsView projectId={projectId} runId={runId || overview?.runs[0]?.run_id || ""} runs={overview?.runs || []} prefs={prefs} author={author} projectPath={workspace.startsWith("sugar-workspace://") ? "" : workspace} onSelectRun={setRunId} onOpenActivity={(id) => { setRunId(id); changePage("activity"); }} onOpenResearch={() => changePage("research")} onRunStarted={handleRunStarted} onError={setError} />}
        {page === "network" && <InstitutionsPage projectId={projectId} runs={overview?.runs || []} author={author} onError={setError} onOpenMap={() => changePage("map")} openId={openInstitution} onOpened={() => setOpenInstitution("")} />}
        {page === "map" && <MapPage projectId={projectId} dark={prefs.theme === "dark"} onOpenInstitutions={() => changePage("network")} onOpenRecord={(id) => { setOpenInstitution(id); changePage("network"); }} />}
        {page === "projects" && <ProjectsPage projects={projects} currentId={projectId} loading={projectsLoading} advanced={prefs.mode === "advanced"} createSignal={createSignal} onOpen={openProject} onCreate={async (name, question) => { await createProject(name, question); }} onOpenFolder={() => void openFolder()} onRefresh={() => void loadProjects()} />}
        {page === "timeline" && <TimelinePage projectId={projectId} refreshKey={timelineKey} />}
        {page === "about" && <AboutPage version="1.4" engineVersion={engineVersion} />}
        {page === "settings" && <SettingsPage onRunSetup={() => setShowSetup(true)} prefs={prefs} onSavePrefs={savePrefs} onDirtyChange={(dirty) => { settingsDirty.current = dirty; }} engineState={engineState} apiUrl={apiUrl} apiToken={apiToken} onApiUrl={setApiUrl} onApiToken={setApiToken} onConnect={() => void connectResearchEngine()} busy={Boolean(busy)} onError={setError} />}


        {paletteOpen && <CommandPalette commands={commands} onClose={() => setPaletteOpen(false)} />}
        {helpOpen && <ShortcutHelp onClose={() => setHelpOpen(false)} />}
        <ToastHost toasts={toasts} onDismiss={(id) => setToasts((current) => current.filter((t) => t.id !== id))} />
        {(showSetup || (!prefs.onboarded && engineState === "ready")) && <Onboarding prefs={prefs} onSavePrefs={savePrefs} onOpenSettings={() => changePage("settings")}
          onFinish={() => setShowSetup(false)} onTryExample={(text) => { setPrefill((p) => ({ text, n: p.n + 1 })); changePage("research"); }} />}
        <footer className="statusbar"><div><span className={`status-dot ${workspace ? "active" : "unknown"}`} /><span>{workspace ? (workspace.startsWith("sugar-workspace://") ? `Project · ${projectName}` : `Workspace · ${workspace.split(/[\\/]/).at(-1)}`) : "No project open"}</span></div><span className="statusbar-right">SUGAR research engine <b>·</b> Python core</span></footer>
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
