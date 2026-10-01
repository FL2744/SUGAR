import { api, apiPost, openEventStream } from "./bridge";
import type {
  ActivityEvent, ConnectionReport, Interpretation, PlanSpec, PlatformRow, ProjectOverview, ProviderProfileRow, ProviderType,
  CodeRow, CodingSummary, Digest, Monitor, InstitutionCandidate, InstitutionDetail, InstitutionList, NetworkPreview, NetworkRow, OverlapResult, SeedRow, ResultItem, ResultsPayload, ReviewState, ReviewSummary, RunSummary, TimelineEvent,
} from "./research-types";

const ws = (id: string) => `/api/workspaces/${encodeURIComponent(id)}`;
const query = (params: Record<string, string | number | boolean | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== "" && value !== false) search.set(key, String(value));
  const text = search.toString();
  return text ? `?${text}` : "";
};

export const research = {
  platforms: () => api<{ platforms: PlatformRow[] }>("/api/platforms").then((r) => r.platforms),
  setPlatformCredential: (key: string, value: string) => apiPost<{ platforms: PlatformRow[] }>("/api/platform-credentials", { key, value }).then((r) => r.platforms),
  providers: () => api<{ profiles: ProviderProfileRow[]; default_profile_id: string; types: ProviderType[]; credential_storage: string }>("/api/providers"),
  saveProvider: (profile: Partial<ProviderProfileRow>, secret: string | null, makeDefault = false) =>
    apiPost<{ profile: ProviderProfileRow; default_profile_id: string }>("/api/providers", { profile, secret, make_default: makeDefault }),
  testProvider: (id: string) => apiPost<{ report: ConnectionReport; profile: ProviderProfileRow }>(`/api/providers/${encodeURIComponent(id)}/test`),
  testDraftProvider: (profile: Partial<ProviderProfileRow>, secret: string) => apiPost<{ report: ConnectionReport }>("/api/providers/test", { profile, secret }).then((r) => r.report),
  deleteProvider: (id: string) => api<{ default_profile_id: string }>(`/api/providers/${encodeURIComponent(id)}`, { method: "DELETE" }),
  setDefaultProvider: (id: string) => apiPost<{ default_profile_id: string }>("/api/providers/default", { profile_id: id }),
  diagnostics: () => api<{ report: string }>("/api/diagnostics/report").then((r) => r.report),

  interpret: (text: string, mode: "auto" | "deterministic", workspaceId = "", providerId = "") =>
    apiPost<Interpretation>("/api/interpret", { text, mode, workspace_id: workspaceId || undefined, provider_id: providerId || undefined }),
  manualPlan: (fields: Record<string, unknown>) => apiPost<{ plan: PlanSpec | null; summary: Interpretation["summary"]; issues: Interpretation["issues"] }>("/api/plan/manual", { fields }),
  normalizePlan: (plan: PlanSpec) => apiPost<{ plan: PlanSpec; summary: Interpretation["summary"]; issues: Interpretation["issues"] }>("/api/plan/normalize", { plan }),

  overview: (id: string) => api<ProjectOverview>(`${ws(id)}/research`),
  savePlan: (id: string, plan: PlanSpec, reason: string, request = "") =>
    apiPost<{ plan: PlanSpec; summary: Interpretation["summary"]; issues: Interpretation["issues"] }>(`${ws(id)}/research/plan`, { plan, reason, request }),
  rebuildPlan: (id: string) => apiPost<Interpretation>(`${ws(id)}/research/rebuild-plan`),
  reinterpret: (id: string, mode: "auto" | "deterministic" = "auto") => apiPost<Interpretation>(`${ws(id)}/research/reinterpret`, { mode }),
  saveSettings: (id: string, changes: Record<string, unknown>) => apiPost<{ settings: ProjectOverview["settings"] }>(`${ws(id)}/research/settings`, { changes }),
  addNote: (id: string, text: string, author: string, itemId = "", runId = "") => apiPost<{ note: Record<string, unknown> }>(`${ws(id)}/research/notes`, { text, author, item_id: itemId, run_id: runId }),
  timeline: (id: string, limit = 100) => api<{ events: TimelineEvent[] }>(`${ws(id)}/timeline${query({ limit })}`).then((r) => r.events),

  startRun: (id: string, body: { kind?: string; parent_run_id?: string; plan?: PlanSpec; debug?: boolean } = {}) => apiPost<{ run: RunSummary }>(`${ws(id)}/runs`, body).then((r) => r.run),
  runs: (id: string) => api<{ runs: RunSummary[] }>(`${ws(id)}/runs`).then((r) => r.runs),
  run: (id: string, runId: string) => api<{ run: RunSummary }>(`${ws(id)}/runs/${runId}`).then((r) => r.run),
  events: (id: string, runId: string, after = 0, filters: Record<string, string> = {}) =>
    api<{ events: ActivityEvent[]; last_seq: number; finished: boolean; live: boolean }>(`${ws(id)}/runs/${runId}/events${query({ after, limit: 2000, ...filters })}`),
  control: (id: string, runId: string, body: Record<string, unknown>) => apiPost<{ run: RunSummary }>(`${ws(id)}/runs/${runId}/control`, body).then((r) => r.run),
  review: (id: string, itemId: string) => api<{ item_id: string; review: ReviewState }>(`${ws(id)}/research/review${query({ item_id: itemId })}`),
  postReview: (id: string, itemId: string, action: Record<string, unknown>, author = "") =>
    apiPost<{ item_id: string; review: ReviewState; summary: ReviewSummary }>(`${ws(id)}/research/review`, { item_id: itemId, author, ...action }),
  institutions: (id: string, params: Record<string, string | number | boolean | undefined> = {}) => api<InstitutionList>(`${ws(id)}/research/institutions${query(params)}`),
  institution: (id: string, entityId: string) => api<{ institution: InstitutionDetail }>(`${ws(id)}/research/institutions/${encodeURIComponent(entityId)}`).then((r) => r.institution),
  recordInstitution: (id: string, body: { values: Record<string, unknown>; evidence: Array<Record<string, unknown>>; entity_id?: string; author?: string }) =>
    apiPost<{ institution: InstitutionDetail }>(`${ws(id)}/research/institutions`, body).then((r) => r.institution),
  reviewClaim: (id: string, entityId: string, claimId: string, state: string, note = "", author = "") =>
    apiPost<{ institution: InstitutionDetail }>(`${ws(id)}/research/institutions/${encodeURIComponent(entityId)}/review`, { claim_id: claimId, state, note, author }).then((r) => r.institution),
  mergeInstitutions: (id: string, keepId: string, dropId: string, reason = "", author = "") =>
    apiPost<{ institution: InstitutionDetail }>(`${ws(id)}/research/institutions/${encodeURIComponent(keepId)}/merge`, { drop_id: dropId, reason, author }).then((r) => r.institution),
  institutionCandidates: (id: string, runId: string, mode: "auto" | "deterministic") =>
    apiPost<{ candidates: InstitutionCandidate[]; warnings: string[]; scanned: number; model_used: boolean }>(`${ws(id)}/research/institutions/candidates`, { run_id: runId, mode }),
  institutionHistory: (id: string, entityId: string) => apiPost<{ pages: Array<{ url: string; signals: string[]; total: number; first_seen: string; last_ok: string; snapshots: Array<{ captured_at: string; status: string; archive_url: string }> }>; errors: Array<{ url: string; reason: string }>; note: string }>(`${ws(id)}/research/institutions/${encodeURIComponent(entityId)}/history`, {}),
  networks: (id: string) => api<{ networks: NetworkRow[] }>(`${ws(id)}/research/networks`).then((r) => r.networks),
  setNetwork: (id: string, name: string, role: "subject" | "reference", label = "") => apiPost<{ networks: NetworkRow[] }>(`${ws(id)}/research/networks`, { name, role, label }).then((r) => r.networks),
  previewNetworkFile: (id: string, filename: string, contentBase64: string) => apiPost<NetworkPreview>(`${ws(id)}/research/networks/preview`, { filename, content_base64: contentBase64 }),
  importNetworkFile: (id: string, body: Record<string, unknown>) => apiPost<Record<string, unknown>>(`${ws(id)}/research/networks/import`, body),
  seedSearch: (id: string, source: "wikidata" | "osm", queryText: string, countryCode = "") => apiPost<{ rows: SeedRow[] }>(`${ws(id)}/research/networks/seed`, { source, query: queryText, country_code: countryCode }).then((r) => r.rows),
  seedImport: (id: string, rows: SeedRow[], network: string, role: "subject" | "reference") => apiPost<{ imported: string[]; skipped: number }>(`${ws(id)}/research/networks/seed/import`, { rows, network, role }),
  overlap: (id: string, params: Record<string, string | number | boolean | undefined>) => api<OverlapResult>(`${ws(id)}/research/overlap${query(params)}`),
  coding: (id: string, itemId: string) => api<{ codes: CodeRow[] }>(`${ws(id)}/research/coding${query({ item_id: itemId })}`).then((r) => r.codes),
  codingSummary: (id: string, runId: string) => api<CodingSummary>(`${ws(id)}/research/coding${query({ run_id: runId })}`),
  runCoding: (id: string, runId: string, mode: "auto" | "deterministic") => apiPost<{ items: number; proposed: number; with_codes: number; model_used: boolean; warnings: string[] }>(`${ws(id)}/research/coding/run`, { run_id: runId, mode }),
  decideCode: (id: string, itemId: string, runId: string, field: string, label: string, decision: "confirm" | "reject", quote = "", author = "") =>
    apiPost<{ codes: CodeRow[] }>(`${ws(id)}/research/coding/decide`, { item_id: itemId, run_id: runId, field, label, decision, quote, author }).then((r) => r.codes),
  applyCodes: (id: string, runId: string, itemId: string, entityId: string, author = "") => apiPost<{ applied: string[] }>(`${ws(id)}/research/coding/apply`, { run_id: runId, item_id: itemId, entity_id: entityId, author }),
  monitors: (id: string) => api<{ monitors: Monitor[]; cadences_hours: number[] }>(`${ws(id)}/research/monitors`),
  saveMonitor: (id: string, body: Record<string, unknown>) => apiPost<{ monitor: Monitor; monitors: Monitor[] }>(`${ws(id)}/research/monitors`, body),
  deleteMonitor: (id: string, monitorId: string) => apiPost<{ monitors: Monitor[] }>(`${ws(id)}/research/monitors`, { id: monitorId, delete: true }),
  runMonitor: (id: string, monitorId: string) => apiPost<{ run_id: string; kind: string }>(`${ws(id)}/research/monitors/run`, { id: monitorId }),
  tickMonitors: (id: string) => apiPost<{ started: string[]; digests: string[] }>(`${ws(id)}/research/monitors/tick`, {}),
  digests: (id: string) => api<{ digests: Digest[] }>(`${ws(id)}/research/digests`).then((r) => r.digests),
  checkpointDigest: (id: string) => apiPost<{ digest: Digest }>(`${ws(id)}/research/digests/checkpoint`, {}).then((r) => r.digest),
  geocodeInstitutions: (id: string) => apiPost<{ placed: string[]; failed: Array<{ entity_id: string; reason: string }> }>(`${ws(id)}/research/institutions/geocode`, {}),
  results: (id: string, runId: string, params: Record<string, string | number | boolean | undefined> = {}) => api<ResultsPayload>(`${ws(id)}/runs/${runId}/results${query(params)}`),
  item: (id: string, runId: string, itemId: string) => api<{ item: ResultItem }>(`${ws(id)}/runs/${runId}/items/${itemId}`).then((r) => r.item),
  exportRun: (id: string, runId: string) => apiPost<{ archive: string; directory: string; files: string[] }>(`${ws(id)}/runs/${runId}/export`),
};

export type StreamHandlers = {
  onEvent: (event: ActivityEvent) => void;
  onProgress?: (progress: Partial<RunSummary>) => void;
  onEnd?: (status: string) => void;
  onError?: (message: string) => void;
};

/**
 * Follow a run's activity. Uses the Server-Sent Events stream (fetch-based so the API token header can be
 * sent) and falls back to polling /events if streaming is unavailable. Returns a function that stops it.
 */
export function followRun(workspaceId: string, runId: string, after: number, handlers: StreamHandlers): () => void {
  const controller = new AbortController();
  let cursor = after;
  let stopped = false;

  const poll = async () => {
    while (!stopped) {
      try {
        const page = await research.events(workspaceId, runId, cursor);
        for (const event of page.events) { cursor = Math.max(cursor, event.seq); handlers.onEvent(event); }
        const run = await research.run(workspaceId, runId);
        handlers.onProgress?.(run);
        if (page.finished && page.events.length === 0) { handlers.onEnd?.(run.status); return; }
      } catch (issue) {
        handlers.onError?.(issue instanceof Error ? issue.message : String(issue));
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  };

  const stream = async () => {
    try {
      const response = await openEventStream(`${ws(workspaceId)}/runs/${runId}/stream${query({ after })}`, controller.signal);
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let split: number;
        while ((split = buffer.indexOf("\n\n")) >= 0) {
          const frame = buffer.slice(0, split);
          buffer = buffer.slice(split + 2);
          let name = "message";
          const data: string[] = [];
          for (const line of frame.split("\n")) {
            if (line.startsWith("event:")) name = line.slice(6).trim();
            else if (line.startsWith("data:")) data.push(line.slice(5).trim());
          }
          if (!data.length) continue;
          const payload = JSON.parse(data.join("\n"));
          if (name === "activity") { cursor = Math.max(cursor, payload.seq); handlers.onEvent(payload as ActivityEvent); }
          else if (name === "progress") handlers.onProgress?.(payload);
          else if (name === "end") { handlers.onEnd?.(String(payload.status || "")); return; }
        }
      }
      if (!stopped) await poll();            // stream closed without an end frame: confirm the state by polling
    } catch (issue) {
      if (stopped) return;
      handlers.onError?.(issue instanceof Error ? issue.message : String(issue));
      await poll();
    }
  };

  void stream();
  return () => { stopped = true; controller.abort(); };
}
