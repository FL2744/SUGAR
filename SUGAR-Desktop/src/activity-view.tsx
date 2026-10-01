import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { followRun, research } from "./research-api";
import type { ActivityEvent, RunSummary, SourceRow } from "./research-types";
import type { Prefs } from "./prefs";
import { ItemInspector } from "./item-inspector";
import { CopyButton, EmptyState, IncompleteNotice, Pill, Spinner, StatusPill, duration, formatTime, languageName, platformLabel, titleCase } from "./ui";

const STAGES = [
  { id: "plan", label: "Plan", detail: (c: Counts) => `${c.sources_total || 0} platforms · ${c.queries_total || 0} searches` },
  { id: "search", label: "Search", detail: (c: Counts) => `${c.queries_done || 0} / ${c.queries_total || 0} searches` },
  { id: "collect", label: "Collect", detail: (c: Counts) => `${c.collected || 0} items` },
  { id: "translate", label: "Translate", detail: (c: Counts) => `${c.translated || 0} done${c.translation_pending ? ` · ${c.translation_pending} waiting` : ""}` },
  { id: "process", label: "Process", detail: (c: Counts) => `${c.processed || 0} processed` },
  { id: "results", label: "Results", detail: (c: Counts) => `${c.collected || 0} kept` },
] as const;

type Counts = Record<string, number>;
type ItemState = { id: string; source: string; url: string; snippet: string; query: string; language: string; state: string; reason: string; translated: boolean; seq: number };
type TranslationCard = { seq: number; itemId: string; source: string; from: string; to: string; original: string; translation: string; provider: string; model: string; ts: string; ms: number; url: string };
type View = {
  events: ActivityEvent[];
  items: Record<string, ItemState>;
  itemOrder: string[];
  translations: TranslationCard[];
  translating: Record<string, { itemId: string; from: string; ts: string }>;
  searching: Record<string, string>;
  lagSamples: number[];
};

const EMPTY: View = { events: [], items: {}, itemOrder: [], translations: [], translating: {}, searching: {}, lagSamples: [] };
const MAX_EVENTS = 4000;

function reduce(state: View, action: { type: "events"; events: ActivityEvent[] } | { type: "reset" }): View {
  if (action.type === "reset") return EMPTY;
  const items = { ...state.items };
  const itemOrder = [...state.itemOrder];
  const translations = [...state.translations];
  const translating = { ...state.translating };
  const searching = { ...state.searching };
  const lagSamples = [...state.lagSamples];
  const known = new Set(state.events.slice(-200).map((e) => e.seq));
  const fresh = action.events.filter((event) => !known.has(event.seq));
  for (const event of fresh) {
    const d = event.data || {};
    if (typeof event.lag_ms === "number") lagSamples.push(event.lag_ms);
    switch (event.type) {
      case "item.discovered":
        if (!items[d.item_id]) { itemOrder.push(d.item_id); items[d.item_id] = { id: d.item_id, source: event.source, url: d.url || "", snippet: event.message, query: d.query || "", language: "", state: "discovered", reason: "", translated: false, seq: event.seq }; }
        break;
      case "language.detected": if (items[d.item_id]) items[d.item_id] = { ...items[d.item_id], language: d.language, state: "collected" }; break;
      case "item.rejected": if (items[d.item_id]) items[d.item_id] = { ...items[d.item_id], state: "rejected", reason: d.reason || event.message }; break;
      case "duplicate.detected": if (items[d.item_id] && d.kind !== "same_item") items[d.item_id] = { ...items[d.item_id], state: "duplicate", reason: event.message }; break;
      case "item.excluded": if (items[d.item_id]) items[d.item_id] = { ...items[d.item_id], state: "excluded", reason: d.reason || "Excluded" }; break;
      case "translation.started": translating[d.item_id] = { itemId: d.item_id, from: d.source_language, ts: event.ts }; break;
      case "translation.failed": case "translation.skipped": delete translating[d.item_id]; break;
      case "translation.completed":
        delete translating[d.item_id];
        if (items[d.item_id]) items[d.item_id] = { ...items[d.item_id], translated: true };
        translations.unshift({ seq: event.seq, itemId: d.item_id, source: event.source, from: d.source_language, to: d.target_language, original: d.original || "", translation: d.translation || "", provider: d.provider || "", model: d.model || "", ts: event.ts, ms: d.ms || 0, url: d.url || "" });
        break;
      case "source.search.started": searching[event.source] = `Searching ${platformLabel(event.source)} for “${d.dispatched || d.query}”`; break;
      case "source.search.completed": case "source.failed": delete searching[event.source]; break;
      case "source.retry.scheduled": case "provider.rate_limited": searching[event.source] = event.message; break;
      case "pipeline.completed": case "run.cancelled": for (const key of Object.keys(searching)) delete searching[key]; break;
      default: break;
    }
  }
  const events = [...state.events, ...fresh].slice(-MAX_EVENTS);
  return { events, items, itemOrder: itemOrder.slice(-1500), translations: translations.slice(0, 300), translating, searching, lagSamples: lagSamples.slice(-300) };
}

const TIMING_LABELS: Record<string, string> = { llm_call: "Model calls", ui_delivery: "UI event delivery", deduplication: "De-duplication", search: "Search (platform requests)", download: "Download / retrieval", parsing: "Parsing", extraction: "Extraction", translation: "Translation", serialization: "Saving", interpretation: "Interpretation" };

const EVENT_ICON: Record<string, string> = {
  "run.started": "▶", "run.paused": "⏸", "run.resumed": "▶", "run.cancelling": "■", "run.cancelled": "■", "run.failed": "✕", "pipeline.completed": "✓",
  "research.plan.created": "☷", "query.generated": "⌕", "query.disabled": "⊘", "research.plan.updated": "✎",
  "source.search.started": "↗", "source.search.completed": "✓", "source.failed": "✕", "source.skipped": "⊘", "source.retry.scheduled": "↻", "provider.rate_limited": "⏳",
  "item.discovered": "◆", "item.download.completed": "⇩", "item.rejected": "−", "item.excluded": "⊘", "item.changed": "≠", "duplicate.detected": "⧉",
  "language.detected": "文", "translation.started": "⇄", "translation.completed": "⇄", "translation.failed": "!", "translation.skipped": "!",
  "extraction.started": "¶", "extraction.completed": "¶", "stage.started": "›", "stage.completed": "✓", "provider.call": "λ", "collector.request": "⚙", "parser.decision": "⚙", "timing.recorded": "⏱",
};

function describe(event: ActivityEvent): string {
  if (event.message) return event.message;
  const d = event.data || {};
  switch (event.type) {
    case "item.download.started": return `Retrieving ${d.url || "item"}`;
    case "item.download.completed": return `Retrieved ${d.url || "item"}`;
    case "extraction.started": return "Extracting text";
    default: return titleCase(event.type.replaceAll(".", " "));
  }
}

const SEVERITY_CLASS: Record<string, string> = { info: "", warning: "sev-warn", error: "sev-error" };

function StageBar({ run, counts }: { run: RunSummary; counts: Counts }) {
  const states = run.stage_states || {};
  return (
    <ol className="stage-bar" aria-label="Pipeline stages">
      {STAGES.map((stage, index) => {
        const state = states[stage.id]?.state || "pending";
        const live = state === "running" && !run.paused && ["running", "queued"].includes(run.status);
        return (
          <li key={stage.id} className={`stage stage-${state} ${live ? "live" : ""}`} aria-current={live ? "step" : undefined}>
            <span className="stage-dot" aria-hidden="true">{state === "done" ? "✓" : state === "failed" ? "✕" : state === "skipped" ? "–" : live ? <Spinner /> : index + 1}</span>
            <span className="stage-copy"><strong>{stage.label}</strong><small>{state === "skipped" ? "skipped" : state === "pending" ? "waiting" : stage.detail(counts)}</small></span>
          </li>);
      })}
    </ol>
  );
}

function SourcesPanel({ run, searching, onRetry, canRetry }: { run: RunSummary; searching: Record<string, string>; onRetry: (source: string) => void; canRetry: boolean }) {
  const sources = Object.entries(run.sources || {}) as Array<[string, SourceRow]>;
  if (!sources.length) return <p className="muted small-pad">Platforms appear here once the plan is resolved.</p>;
  return (
    <ul className="source-cards">
      {sources.map(([name, row]) => {
        const tone = row.status === "success" ? "ok" : row.status === "running" ? "busy" : row.status === "zero_result" ? "neutral" : row.status === "skipped" ? "warn" : row.status === "pending" ? "neutral" : "error";
        const retryable = ["failed", "partial"].includes(row.status) && canRetry;
        return (
          <li key={name} className={`source-card tone-${tone}`}>
            <div className="source-card-head"><strong>{platformLabel(name)}</strong><Pill tone={tone as "ok"}>{titleCase(row.status.replace("zero_result", "no results"))}</Pill></div>
            <div className="source-card-stats">{row.items} item{row.items === 1 ? "" : "s"} · {row.queries_run} quer{row.queries_run === 1 ? "y" : "ies"}{row.queries_failed ? ` · ${row.queries_failed} failed` : ""}</div>
            {searching[name] && <div className="source-card-live">{searching[name]}</div>}
            {row.error?.message && <div className="source-card-error">{String(row.error.message)}</div>}
            {retryable && <button className="button button-secondary button-small" onClick={() => onRetry(name)}>Retry {platformLabel(name)}</button>}
          </li>);
      })}
    </ul>
  );
}

function TranslationList({ cards, translating, onInspect, itemLanguages }: { cards: TranslationCard[]; translating: View["translating"]; onInspect: (id: string) => void; itemLanguages: Record<string, string> }) {
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const current = Object.values(translating);
  if (!cards.length && !current.length) return <EmptyState icon="⇄" title="No translations yet">Items in other languages appear here — original beside its translation — as they are translated.</EmptyState>;
  return (
    <div className="translation-list">
      {current.map((t) => <div className="translation-pending" key={t.itemId}><Spinner /> Translating an item from {languageName(t.from || itemLanguages[t.itemId] || "und")}…</div>)}
      {cards.map((card) => {
        const expanded = open[card.seq];
        const clip = (text: string) => (expanded || text.length <= 320 ? text : text.slice(0, 320) + "…");
        return (
          <article className="translation-card" key={card.seq}>
            <div className="translation-cols">
              <div><span className="eyebrow">ORIGINAL · {languageName(card.from)}</span><p dir="auto">{clip(card.original)}</p></div>
              <div><span className="eyebrow">TRANSLATION · {card.to}</span><p dir="auto">{clip(card.translation)}</p></div>
            </div>
            <footer><span>{platformLabel(card.source)}</span><span>{card.provider} · {card.model}</span><span>{formatTime(card.ts, true)}</span><span>{card.ms ? duration(card.ms) : ""}</span>
              {(card.original.length > 320 || card.translation.length > 320) && <button className="text-button" onClick={() => setOpen({ ...open, [card.seq]: !expanded })}>{expanded ? "Collapse" : "Expand"}</button>}
              <button className="text-button" onClick={() => onInspect(card.itemId)}>Inspect</button></footer>
          </article>);
      })}
    </div>
  );
}

export function ActivityView({ projectId, runId, prefs, author, onOpenResults, onNewRun, onOpenSettings, onRunStarted, onRunSettled, onError }: {
  projectId: string; runId: string; prefs: Prefs; author: string; onRunSettled?: (run: RunSummary) => void;
  onOpenResults: (runId: string) => void; onNewRun: () => void; onOpenSettings: () => void;
  onRunStarted: (projectId: string, run: RunSummary) => void; onError: (message: string) => void;
}) {
  const [run, setRun] = useState<RunSummary | null>(null);
  const [view, dispatch] = useReducer(reduce, EMPTY);
  const [tab, setTab] = useState<"feed" | "translations" | "items" | "warnings" | "searches" | "debug">("feed");
  const [filters, setFilters] = useState({ stage: "", source: "", severity: "", text: "" });
  const [follow, setFollow] = useState(true);
  const [inspect, setInspect] = useState("");
  const [now, setNow] = useState(Date.now());
  const [newQuery, setNewQuery] = useState("");
  const [busy, setBusy] = useState("");
  const [connection, setConnection] = useState<"live" | "reconnecting" | "closed">("closed");
  const feedRef = useRef<HTMLDivElement>(null);
  const buffer = useRef<ActivityEvent[]>([]);
  const advanced = prefs.mode === "advanced";

  const active = Boolean(run && ["queued", "running", "paused", "cancelling"].includes(run.status));

  // Tell the shell when a run reaches a final state so the sidebar and top bar stop showing "running".
  const settledKey = useRef("");
  useEffect(() => {
    if (!run || active) return;
    const key = `${run.run_id}:${run.status}`;
    if (settledKey.current !== key) { settledKey.current = key; onRunSettled?.(run); }
  }, [run, active, onRunSettled]);

  // Batch incoming events so a burst of hundreds does not re-render the page for every one of them.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (buffer.current.length) { const batch = buffer.current; buffer.current = []; dispatch({ type: "events", events: batch }); }
    }, 150);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);

  useEffect(() => {
    if (!projectId || !runId) return;
    let stop: (() => void) | undefined;
    let cancelled = false;
    dispatch({ type: "reset" }); buffer.current = []; setRun(null);
    void (async () => {
      try {
        const [initialRun, page] = await Promise.all([research.run(projectId, runId), research.events(projectId, runId, 0)]);
        if (cancelled) return;
        setRun(initialRun);
        dispatch({ type: "events", events: page.events });
        const terminal = ["completed", "completed_with_warnings", "failed", "cancelled"].includes(initialRun.status);
        if (terminal) { setConnection("closed"); return; }
        setConnection("live");
        stop = followRun(projectId, runId, page.last_seq, {
          onEvent: (event) => { buffer.current.push(event); setConnection("live"); },
          onProgress: (progress) => setRun((current) => (current ? { ...current, ...progress } : current)),
          onEnd: () => { setConnection("closed"); void research.run(projectId, runId).then((finished) => { if (!cancelled) setRun(finished); }); },
          onError: () => setConnection("reconnecting"),
        });
      } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); }
    })();
    return () => { cancelled = true; stop?.(); };
  }, [projectId, runId, onError]);

  useEffect(() => { if (follow && feedRef.current && tab === "feed") feedRef.current.scrollTop = feedRef.current.scrollHeight; }, [view.events.length, follow, tab]);

  const counts: Counts = useMemo(() => {
    const base: Counts = { ...(run?.counts || {}) };
    if (!Object.keys(base).length) {
      const items = Object.values(view.items);
      base.collected = items.filter((i) => i.state === "collected").length;
    }
    return base;
  }, [run, view.items]);

  const control = useCallback(async (body: Record<string, unknown>, label: string) => {
    setBusy(label);
    try {
      const updated = await research.control(projectId, runId, body);
      if (updated.run_id !== runId) onRunStarted(projectId, updated); else setRun((current) => (current ? { ...current, ...updated } : updated));
    } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  }, [projectId, runId, onError, onRunStarted]);

  const startOperation = async (kind: string) => {
    setBusy(kind);
    try { onRunStarted(projectId, await research.startRun(projectId, { kind, parent_run_id: runId, debug: prefs.debug })); }
    catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };

  if (!runId) return (
    <section className="page-content"><EmptyState icon="↗" title="No research is running" action={<button className="button button-primary" onClick={onNewRun}>Start a research request</button>}>
      Live progress appears here while a run works: each search, source, and translation as it happens.</EmptyState></section>);
  if (!run) return <section className="page-content"><div className="loading-block"><Spinner /> Loading run…</div></section>;

  const started = run.started_at ? new Date(run.started_at).getTime() : now;
  const ended = run.finished_at ? new Date(run.finished_at).getTime() : now;
  const elapsed = Math.max(0, ended - started);
  const searchingNow = Object.values(view.searching);
  const statusLine = run.status === "paused" ? "Paused — work in progress will finish, nothing new starts." : active
    ? (searchingNow[0] || (Object.keys(view.translating).length ? "Translating collected items…" : `Stage: ${titleCase(run.stage)}`))
    : run.status === "cancelled" ? "Cancelled — results collected so far were kept." : run.status === "failed" ? "The run could not finish. See the warnings below." : "Finished.";
  const languageOf = Object.fromEntries(Object.values(view.items).map((i) => [i.id, i.language]));
  const sourceNames = Object.keys(run.sources || {});
  const filtered = view.events.filter((e) => (!filters.stage || e.stage === filters.stage) && (!filters.source || e.source === filters.source)
    && (!filters.severity || e.severity === filters.severity) && (!filters.text || `${e.message} ${e.type}`.toLowerCase().includes(filters.text.toLowerCase()))
    && (prefs.debug || !["provider.call", "collector.request", "parser.decision", "timing.recorded"].includes(e.type)));
  const problems = view.events.filter((e) => e.severity !== "info");
  const items = view.itemOrder.map((id) => view.items[id]).reverse();
  const lag = view.lagSamples.length ? view.lagSamples.reduce((a, b) => a + b, 0) / view.lagSamples.length : 0;
  const plan = run.plan;
  const queries = run.generated_searches || [];
  const disabledIds = new Set(view.events.filter((e) => e.type === "query.disabled" && !e.data.skipped).map((e) => e.data.query_id));

  return (
    <section className="page-content activity-page">
      <div className="page-heading compact-heading">
        <div><div className="eyebrow">RESEARCH ACTIVITY <span className="eyebrow-line" /></div>
          <h1>{plan?.topic ? titleCase(plan.topic) : "Research run"}</h1>
          <p>{titleCase(run.kind)} · started {formatTime(run.started_at)} · {duration(elapsed)}{run.parent_run_id ? ` · from ${run.parent_run_id}` : ""}</p></div>
        <div className="run-controls">
          <StatusPill status={run.status} />
          {active && run.status === "running" && <button className="button button-secondary" disabled={Boolean(busy)} onClick={() => void control({ action: "pause" }, "pause")}>⏸ Pause</button>}
          {run.status === "paused" && <button className="button button-primary" disabled={Boolean(busy)} onClick={() => void control({ action: "resume" }, "resume")}>▶ Resume</button>}
          {active && <button className="button button-quiet danger" disabled={Boolean(busy) || run.status === "cancelling"} onClick={() => { if (window.confirm("Cancel this run? Results collected so far are kept.")) void control({ action: "cancel" }, "cancel"); }}>Cancel</button>}
          {!active && <button className="button button-primary" onClick={() => onOpenResults(runId)}>View results →</button>}
        </div>
      </div>

      <div className="status-line" role="status" aria-live="polite">{active && <Spinner />}<span>{statusLine}</span>
        {active && <span className={`connection-dot conn-${connection}`} title={connection === "live" ? "Receiving live updates" : "Reconnecting…"}>{connection === "live" ? "live" : "reconnecting"}</span>}</div>
      <StageBar run={run} counts={counts} />

      <div className="counter-row" aria-label="Live totals">
        {[["Results found", counts.discovered || 0], ["Kept", counts.collected || 0], ["Queued for translation", counts.translation_pending || 0], ["Processed", counts.processed || 0],
          ["Translated", counts.translated || 0], ["Rejected", counts.rejected || 0], ["Duplicates", counts.duplicates || 0], ["Warnings", (counts.warnings || 0) + (counts.errors || 0)]].map(([label, value]) => (
          <div className={`counter ${label === "Warnings" && Number(value) > 0 ? "has-warn" : ""}`} key={String(label)}><strong>{value}</strong><span>{label}</span></div>))}
      </div>

      {!active && run.completeness && !run.completeness.complete && <IncompleteNotice run={run} busy={Boolean(busy)} onRetry={(name) => void control({ action: "retry_source", source: name }, `retry-${name}`)} />}
      {!active && run.completeness?.complete && <div className="notice notice-ok"><strong>Complete.</strong> {run.completeness.summary}</div>}

      <div className="activity-layout">
        <div className="activity-main">
          <div className="tabs" role="tablist" aria-label="Activity sections">
            {([["feed", "Live activity"], ["translations", `Translations (${view.translations.length})`], ["items", `Items (${items.length})`], ["warnings", `Warnings (${problems.length})`],
              ...(advanced ? [["searches", "Searches"]] : []), ...(prefs.debug ? [["debug", "Debug"]] : [])] as Array<[typeof tab, string]>).map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{label}</button>))}
          </div>

          {tab === "feed" && <>
            <div className="filter-bar">
              <select value={filters.stage} onChange={(e) => setFilters({ ...filters, stage: e.target.value })} aria-label="Filter by stage"><option value="">All stages</option>{STAGES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}</select>
              <select value={filters.source} onChange={(e) => setFilters({ ...filters, source: e.target.value })} aria-label="Filter by source"><option value="">All sources</option>{sourceNames.map((s) => <option key={s} value={s}>{platformLabel(s)}</option>)}</select>
              <select value={filters.severity} onChange={(e) => setFilters({ ...filters, severity: e.target.value })} aria-label="Filter by severity"><option value="">All messages</option><option value="warning">Warnings</option><option value="error">Errors</option></select>
              <input value={filters.text} onChange={(e) => setFilters({ ...filters, text: e.target.value })} placeholder="Filter text" aria-label="Filter text" />
              <label className="check-row"><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /><span>Follow live</span></label>
            </div>
            <div className="feed" ref={feedRef} role="log" aria-live="off" aria-label="Activity feed">
              {filtered.length === 0 && <p className="muted small-pad">{active ? "Waiting for the first events…" : "No events match these filters."}</p>}
              {filtered.map((event) => (
                <details className={`feed-row ${SEVERITY_CLASS[event.severity]}`} key={event.seq}>
                  <summary><span className="feed-icon" aria-hidden="true">{EVENT_ICON[event.type] || "•"}</span><time>{formatTime(event.ts, true)}</time>
                    {event.source && <span className="feed-source">{platformLabel(event.source)}</span>}<span className="feed-text">{describe(event)}</span></summary>
                  <div className="feed-detail"><code>{event.type}</code> · stage {event.stage} · #{event.seq}
                    {(advanced || prefs.debug) && <pre className="json-view">{JSON.stringify(event.data, null, 2)}</pre>}</div>
                </details>))}
            </div>
          </>}

          {tab === "translations" && <TranslationList cards={view.translations} translating={view.translating} onInspect={setInspect} itemLanguages={languageOf} />}

          {tab === "items" && (items.length === 0 ? <EmptyState icon="◆" title="No items yet">Discovered items are listed here with their state as soon as they arrive.</EmptyState> :
            <ul className="item-list">{items.slice(0, 400).map((item) => (
              <li key={item.id} className={`item-row item-${item.state}`}>
                <div className="item-meta"><Pill tone={item.state === "rejected" || item.state === "excluded" ? "warn" : item.state === "duplicate" ? "neutral" : "ok"}>{item.translated ? "translated" : item.state}</Pill>
                  <span>{platformLabel(item.source)}</span>{item.language && <span>{languageName(item.language)}</span>}</div>
                <p dir="auto">{item.snippet}</p>
                {item.reason && <small className="muted">{item.reason}</small>}
                <div className="item-actions">
                  {item.url && <a className="text-button" href={item.url} target="_blank" rel="noreferrer">Open source ↗</a>}
                  <button className="text-button" onClick={() => setInspect(item.id)}>Inspect</button>
                  {active && ["collected", "discovered"].includes(item.state) && <button className="text-button" onClick={() => void control({ action: "exclude_item", item_id: item.id, reason: "Excluded by researcher" }, "exclude")}>Exclude</button>}
                </div>
              </li>))}</ul>)}

          {tab === "warnings" && (problems.length === 0 ? <EmptyState icon="✓" title="No warnings">Warnings and errors are listed here, with the platform or subsystem responsible.</EmptyState> :
            <ul className="problem-list">{problems.map((e) => (
              <li key={e.seq} className={`problem sev-${e.severity}`}><strong>{e.source ? platformLabel(e.source) : titleCase(e.stage)}</strong> <time>{formatTime(e.ts, true)}</time><p>{e.message}</p>
                {e.data.classification && <small>{String(e.data.classification).replaceAll("_", " ")}{e.data.retries_exhausted ? " · retries exhausted" : ""}</small>}
                {e.message.includes("Settings") && <button className="text-button" onClick={onOpenSettings}>Open Settings</button>}</li>))}</ul>)}

          {tab === "searches" && (
            <div className="searches-panel">
              <p className="muted">Changes here affect searches that have not started yet. Searches already sent are not undone; edits become part of this run's record.</p>
              <ul className="query-list">{queries.map((q) => { const off = disabledIds.has(q.id) || !q.enabled; return (
                <li key={q.id} className={off ? "off" : ""}><code>{q.text}</code><span className="muted">{[q.platform && `only ${q.platform}`, q.language && languageName(q.language), q.origin].filter(Boolean).join(" · ")}</span>
                  {active && <button className="text-button" onClick={() => void control({ action: off ? "enable_query" : "disable_query", query_id: q.id }, "query")}>{off ? "Enable" : "Disable"}</button>}</li>); })}</ul>
              {active && <div className="note-add"><input value={newQuery} onChange={(e) => setNewQuery(e.target.value)} placeholder="Add a search term or synonym" aria-label="New query" />
                <button className="button button-secondary button-small" disabled={!newQuery.trim()} onClick={() => { void control({ action: "add_query", text: newQuery.trim() }, "query"); setNewQuery(""); }}>Add to remaining searches</button></div>}
            </div>)}

          {tab === "debug" && (
            <div className="debug-panel">
              <div className="debug-actions"><CopyButton text={JSON.stringify({ run: { ...run, stage_states: undefined }, events: view.events.slice(-500) }, null, 2)} label="Copy run + events (redacted)" />
                <button className="button button-quiet button-small" onClick={() => void research.diagnostics().then((text) => navigator.clipboard?.writeText(text))}>Copy diagnostic report</button></div>
              <h4>Timing</h4>
              <table className="data-table"><thead><tr><th>Category</th><th>Calls</th><th>Total</th><th>Average</th><th>Slowest</th></tr></thead>
                <tbody>{Object.entries((run.metrics?.timings || run.timings)?.categories || {}).map(([name, row]) => { const r = row as { count: number; total_ms: number; avg_ms: number; max_ms: number }; return (
                  <tr key={name}><td>{TIMING_LABELS[name] || titleCase(name)}</td><td>{r.count}</td><td>{duration(r.total_ms)}</td><td>{duration(r.avg_ms)}</td><td>{duration(r.max_ms)}</td></tr>); })}
                  <tr><td>UI event delivery (avg)</td><td>{view.lagSamples.length}</td><td colSpan={3}>{lag.toFixed(1)} ms</td></tr></tbody></table>
              <h4>Interpreted plan</h4><pre className="json-view">{JSON.stringify(plan ? { ...plan, queries: `(${plan.queries.length} — see Searches)` } : {}, null, 2)}</pre>
              <h4>Provider and connector calls</h4>
              <ul className="debug-list">{view.events.filter((e) => ["provider.call", "collector.request", "source.search.started", "source.retry.scheduled"].includes(e.type)).slice(-80).map((e) => (
                <li key={e.seq}><code>{e.type}</code> <time>{formatTime(e.ts, true)}</time> {e.source && <span>{e.source}</span>} <small>{e.type === "provider.call" ? `${e.data.purpose} · ${e.data.model} · ${e.data.ms} ms · ${e.data.ok ? "ok" : String(e.data.error)}` : describe(e)}</small></li>))}</ul>
              <h4>Rejections and parser decisions</h4>
              <ul className="debug-list">{view.events.filter((e) => e.type === "parser.decision" || e.type === "item.rejected").slice(-60).map((e) => <li key={e.seq}><code>{e.type}</code> <small>{e.message}</small></li>)}</ul>
              <h4>Errors</h4>
              {(run.errors || []).length === 0 ? <p className="muted">None.</p> : (run.errors || []).map((e, i) => <div key={i} className="error-detail"><strong>{String(e.classification)} · {String(e.stage)} · {String(e.subsystem)}</strong><p>{String(e.message)}</p>{e.traceback ? <pre className="json-view">{String(e.traceback)}</pre> : null}</div>)}
              <p className="muted">Secrets are redacted from everything on this page.</p>
            </div>)}
        </div>

        <aside className="activity-side">
          <section className="panel side-panel"><h3>Platforms</h3><SourcesPanel run={run} searching={view.searching} canRetry={!["cancelling"].includes(run.status)} onRetry={(source) => void control({ action: "retry_source", source }, `retry-${source}`)} /></section>
          {!active && (
            <section className="panel side-panel"><h3>Next</h3>
              <div className="stack-buttons">
                <button className="button button-secondary" disabled={Boolean(busy)} onClick={() => void startOperation("rerun")}>Rerun this plan</button>
                <button className="button button-secondary" disabled={Boolean(busy)} onClick={() => void startOperation("refresh_sources")}>Refresh sources</button>
                <button className="button button-secondary" disabled={Boolean(busy)} onClick={() => void startOperation("reprocess")}>Reprocess results</button>
              </div></section>)}
          <section className="panel side-panel"><h3>Run record</h3>
            <dl className="kv small"><div><dt>Run</dt><dd>{run.run_id}</dd></div><div><dt>Plan</dt><dd>v{run.plan_version} · {run.plan_fingerprint}</dd></div>
              {run.provider_ref?.model && <div><dt>Model</dt><dd>{run.provider_ref.name || run.provider_ref.type} · {run.provider_ref.model}</dd></div>}
              {run.provider_ref && !run.provider_ref.model && <div><dt>Model</dt><dd>none — translation skipped</dd></div>}</dl></section>
        </aside>
      </div>
      {inspect && <ItemInspector projectId={projectId} runId={runId} itemId={inspect} author={author} onClose={() => setInspect("")} />}
    </section>
  );
}
