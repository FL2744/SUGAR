import { api, apiPost, openEventStream } from "./bridge";
import type {
  ActivityEvent, ConnectionReport, Interpretation, PlanSpec, PlatformRow, ProjectOverview, ProviderProfileRow, ProviderType,
  ResultItem, ResultsPayload, RunSummary, TimelineEvent,
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
