import { useMemo, useState, type ReactNode } from "react";
import type { PlanSpec, PlatformRow, ProviderProfileRow, QuerySpec } from "./research-types";
import { ChipInput, Collapsible, Segmented, languageName } from "./ui";

const DEPTH_PRESETS = {
  quick: { query_count: 3, max_posts_per_query: 10, max_pages_per_query: 1 },
  standard: { query_count: 6, max_posts_per_query: 25, max_pages_per_query: 1 },
  deep: { query_count: 12, max_posts_per_query: 50, max_pages_per_query: 3 },
} as const;
const LANGUAGE_SUGGESTIONS = ["en", "ar", "fa", "tr", "he", "fr", "es", "pt", "ru", "zh", "ur", "hi"];

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="field-block"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>;
}

function NumberField({ label, value, onChange, min, max, step = 1, hint }: { label: string; value: number; onChange: (v: number) => void; min: number; max: number; step?: number; hint?: string }) {
  return (
    <Field label={label} hint={hint}>
      <input type="number" value={value} min={min} max={max} step={step} onChange={(event) => { const n = Number(event.target.value); if (Number.isFinite(n)) onChange(Math.min(max, Math.max(min, n))); }} />
    </Field>
  );
}

export function PlanEditor({ plan, platforms, providers, advanced, saving, error, onSave, onCancel }: {
  plan: PlanSpec; platforms: PlatformRow[]; providers: ProviderProfileRow[]; advanced: boolean; saving: boolean; error: string;
  onSave: (plan: PlanSpec) => void; onCancel: () => void;
}) {
  const [draft, setDraft] = useState<PlanSpec>(() => structuredClone(plan));
  const [tab, setTab] = useState<"basic" | "advanced">(advanced ? "advanced" : "basic");
  const patch = (changes: Partial<PlanSpec>) => setDraft((current) => ({ ...current, ...changes }));
  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(plan), [draft, plan]);

  const setDepth = (depth: PlanSpec["depth"]) => setDraft((current) => {
    const old = DEPTH_PRESETS[current.depth];
    const limits = { ...current.limits };
    (Object.keys(old) as Array<keyof typeof old>).forEach((key) => { if (limits[key] === old[key]) limits[key] = DEPTH_PRESETS[depth][key]; });
    return { ...current, depth, limits };
  });
  const updateQuery = (id: string, changes: Partial<QuerySpec>) =>
    patch({ queries: draft.queries.map((q) => (q.id === id ? { ...q, ...changes, origin: changes.enabled !== undefined && Object.keys(changes).length === 1 ? q.origin : "analyst" } : q)) });
  const addQuery = () => patch({ queries: [...draft.queries, { id: `new_${Date.now()}`, text: "", platform: "", language: "", geography: "", origin: "analyst", enabled: true, rationale: "Added by the researcher." }] });
  const togglePlatform = (id: string) => patch({ platforms: draft.platforms.includes(id) ? draft.platforms.filter((p) => p !== id) : [...draft.platforms, id] });
  const enabledCount = draft.queries.filter((q) => q.enabled).length;
  const timeframe = draft.timeframe;

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <section className="modal plan-editor" role="dialog" aria-modal="true" aria-labelledby="plan-editor-title" onClick={(event) => event.stopPropagation()}>
        <header className="modal-head">
          <div><span className="eyebrow">RESEARCH PLAN · v{draft.version}</span><h2 id="plan-editor-title">Edit the plan</h2><p>Changes are validated and saved as a new plan version. Each run records the exact plan it used.</p></div>
          <button className="inspector-close" onClick={onCancel} aria-label="Close plan editor">×</button>
        </header>
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "basic"} className={tab === "basic" ? "on" : ""} onClick={() => setTab("basic")}>Basics</button>
          <button role="tab" aria-selected={tab === "advanced"} className={tab === "advanced" ? "on" : ""} onClick={() => setTab("advanced")}>Advanced configuration</button>
        </div>
        <div className="modal-body">
          {tab === "basic" && <div className="form-stack">
            <Field label="Research topic"><input value={draft.topic} onChange={(event) => patch({ topic: event.target.value })} placeholder="e.g. democracy" /></Field>
            <Field label="Research question" hint="Shown in the project list and reports."><textarea rows={2} value={draft.research_question} onChange={(event) => patch({ research_question: event.target.value })} /></Field>
            <ChipInput label="Regions" values={draft.geography} onChange={(geography) => patch({ geography })} placeholder="Add a country or region, then press Enter" hint="Leave empty for no geographic restriction." />
            <div className="field-block">
              <span>Platforms</span>
              <Segmented label="Platform scope" value={draft.source_scope} onChange={(source_scope) => patch({ source_scope })}
                options={[{ value: "all_enabled", label: "All enabled platforms", hint: "Every platform that has a search collector and credentials" }, { value: "selected", label: "Only these" }]} />
              {draft.source_scope === "selected" && <div className="check-grid">
                {platforms.filter((p) => p.keyword_search).map((p) => (
                  <label key={p.id} className="check-row">
                    <input type="checkbox" checked={draft.platforms.includes(p.id)} onChange={() => togglePlatform(p.id)} />
                    <span>{p.label}</span>
                    {p.state === "needs_credential" && <small className="warn-text">needs credential</small>}
                  </label>))}
              </div>}
            </div>
            <ChipInput label="Languages" values={draft.languages.filter((l) => l !== "auto")} suggestions={LANGUAGE_SUGGESTIONS}
              onChange={(values) => patch({ languages: values.length ? values : ["auto"] })} placeholder="Automatic — add a language code such as ar or fa"
              hint={draft.languages.includes("auto") && draft.languages.length === 1 ? "Automatic: SUGAR detects each item's language." : draft.languages.map(languageName).join(", ")} />
            <div className="field-grid">
              <Field label="From"><input type="date" value={timeframe.start} onChange={(event) => patch({ timeframe: { ...timeframe, start: event.target.value, label: "" } })} /></Field>
              <Field label="Until"><input type="date" value={timeframe.end} onChange={(event) => patch({ timeframe: { ...timeframe, end: event.target.value, label: "" } })} /></Field>
            </div>
            <div className="field-block"><span>Collection depth</span>
              <Segmented label="Depth" value={draft.depth} onChange={setDepth}
                options={[{ value: "quick", label: "Quick", hint: "About 3 queries · 10 posts each" }, { value: "standard", label: "Standard", hint: "About 6 queries · 25 posts each" }, { value: "deep", label: "Deep", hint: "About 12 queries · 50 posts × 3 pages" }]} />
              <small>{draft.limits.query_count} queries · {draft.limits.max_posts_per_query} posts per query · {draft.limits.max_pages_per_query} page(s)</small>
            </div>
            <div className="field-block"><span>Translation</span>
              <Segmented label="Translation policy" value={draft.translation.policy} onChange={(policy) => patch({ translation: { ...draft.translation, policy } })}
                options={[{ value: "auto", label: "Automatic", hint: "Translate non-English items when a provider is configured" }, { value: "always", label: "Always" }, { value: "never", label: "Never" }]} />
            </div>
            <ChipInput label="Exclude" values={draft.exclusions} onChange={(exclusions) => patch({ exclusions })} placeholder="Words or topics to leave out" />
          </div>}

          {tab === "advanced" && <div className="form-stack">
            <Collapsible title="Planned searches" defaultOpen badge={<span className="muted">{enabledCount} of {draft.queries.length} enabled</span>} hint="The exact queries SUGAR will send. Edit, disable, or add your own.">
              <div className="query-table" role="table" aria-label="Planned searches">
                {draft.queries.map((q) => (
                  <div className={`query-row ${q.enabled ? "" : "disabled"}`} role="row" key={q.id}>
                    <input type="checkbox" checked={q.enabled} aria-label={`Enable ${q.text || "query"}`} onChange={(event) => updateQuery(q.id, { enabled: event.target.checked })} />
                    <input className="query-text" value={q.text} placeholder="search terms" aria-label="Query text" onChange={(event) => updateQuery(q.id, { text: event.target.value })} />
                    <select value={q.platform} aria-label="Platform" onChange={(event) => updateQuery(q.id, { platform: event.target.value })}>
                      <option value="">All platforms</option>{platforms.filter((p) => p.keyword_search).map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                    </select>
                    <input className="query-lang" value={q.language} placeholder="lang" aria-label="Language code" maxLength={5} onChange={(event) => updateQuery(q.id, { language: event.target.value })} />
                    <span className={`origin origin-${q.origin}`} title={q.rationale}>{q.origin}</span>
                    <button type="button" className="icon-button" aria-label="Remove query" onClick={() => patch({ queries: draft.queries.filter((x) => x.id !== q.id) })}>×</button>
                    {q.rationale && <small className="query-why">{q.rationale}</small>}
                  </div>))}
                <button type="button" className="button button-secondary button-small" onClick={addQuery}>＋ Add query</button>
              </div>
            </Collapsible>
            <Collapsible title="Sources" hint="Which platforms and how much to take from each">
              <div className="check-grid">
                {platforms.map((p) => (
                  <label key={p.id} className="check-row">
                    <input type="checkbox" disabled={!p.keyword_search} checked={!draft.exclude_platforms.includes(p.id)} onChange={(event) => patch({ exclude_platforms: event.target.checked ? draft.exclude_platforms.filter((x) => x !== p.id) : [...draft.exclude_platforms, p.id] })} />
                    <span>{p.label}</span>
                    <small className={p.state === "ready" ? "ok-text" : "warn-text"}>{p.state === "ready" ? "ready" : p.state === "unsupported" ? "no keyword search" : "needs credential"}</small>
                  </label>))}
              </div>
              <div className="field-grid">
                <NumberField label="Queries to run" value={draft.limits.query_count} min={1} max={60} onChange={(v) => patch({ limits: { ...draft.limits, query_count: v } })} />
                <NumberField label="Posts per query" value={draft.limits.max_posts_per_query} min={1} max={500} onChange={(v) => patch({ limits: { ...draft.limits, max_posts_per_query: v } })} />
                <NumberField label="Pages per query" value={draft.limits.max_pages_per_query} min={1} max={20} onChange={(v) => patch({ limits: { ...draft.limits, max_pages_per_query: v } })} />
                <NumberField label="Total item limit" value={draft.limits.max_items_total} min={1} max={100000} onChange={(v) => patch({ limits: { ...draft.limits, max_items_total: v } })} />
              </div>
              <ChipInput label="Search terms and phrases" values={draft.search_terms} onChange={(search_terms) => patch({ search_terms })} placeholder="Extra terms or synonyms" />
              <ChipInput label="Actors and entities" values={draft.actors} onChange={(actors) => patch({ actors })} placeholder="Organizations or people in scope" />
            </Collapsible>
            <Collapsible title="Translation and language" hint="Translation provider, target language and limits">
              <div className="field-grid">
                <Field label="Translate into"><input value={draft.translation.target_language} onChange={(event) => patch({ translation: { ...draft.translation, target_language: event.target.value } })} /></Field>
                <NumberField label="Parallel translations" value={draft.translation.workers} min={1} max={16} onChange={(v) => patch({ translation: { ...draft.translation, workers: v } })} />
                <NumberField label="Max characters per item" value={draft.translation.max_chars_per_item} min={200} max={20000} step={100} onChange={(v) => patch({ translation: { ...draft.translation, max_chars_per_item: v } })} />
              </div>
              <Field label="LLM provider for this plan" hint="Uses the project default when empty.">
                <select value={draft.provider.profile_id} onChange={(event) => patch({ provider: { ...draft.provider, profile_id: event.target.value } })}>
                  <option value="">Project default</option>{providers.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.effective_model || "no model"}</option>)}
                </select>
              </Field>
              <Field label="Model override" hint="Leave empty to use the provider's model."><input value={draft.provider.model} onChange={(event) => patch({ provider: { ...draft.provider, model: event.target.value } })} /></Field>
              <label className="check-row"><input type="checkbox" checked={draft.provider.use_for_planning} onChange={(event) => patch({ provider: { ...draft.provider, use_for_planning: event.target.checked } })} /><span>Let the model suggest extra queries</span></label>
            </Collapsible>
            <Collapsible title="Extraction, de-duplication and performance">
              <div className="field-grid">
                <NumberField label="Near-duplicate threshold" value={draft.dedup.threshold} min={0.5} max={1} step={0.01} hint="1.00 only merges identical text" onChange={(v) => patch({ dedup: { ...draft.dedup, threshold: v } })} />
                <NumberField label="Minimum characters" value={draft.extraction.min_chars} min={0} max={10000} onChange={(v) => patch({ extraction: { ...draft.extraction, min_chars: v } })} />
                <NumberField label="Parallel platforms" value={draft.concurrency.max_workers} min={1} max={32} onChange={(v) => patch({ concurrency: { ...draft.concurrency, max_workers: v } })} />
                <NumberField label="Delay between queries (s)" value={draft.concurrency.per_source_delay_seconds} min={0} max={60} step={0.5} onChange={(v) => patch({ concurrency: { ...draft.concurrency, per_source_delay_seconds: v } })} />
                <NumberField label="Retry attempts" value={draft.retry.max_attempts} min={1} max={10} onChange={(v) => patch({ retry: { ...draft.retry, max_attempts: v } })} />
                <NumberField label="Retry backoff (s)" value={draft.retry.base_backoff_seconds} min={0} max={3600} onChange={(v) => patch({ retry: { ...draft.retry, base_backoff_seconds: v } })} />
              </div>
              <label className="check-row"><input type="checkbox" checked={draft.dedup.enabled} onChange={(event) => patch({ dedup: { ...draft.dedup, enabled: event.target.checked } })} /><span>Detect duplicates</span></label>
              <label className="check-row"><input type="checkbox" checked={draft.extraction.paragraph_split} onChange={(event) => patch({ extraction: { ...draft.extraction, paragraph_split: event.target.checked } })} /><span>Split long posts into paragraphs (keeps translations traceable)</span></label>
            </Collapsible>
            <Collapsible title="Refresh and listening post" hint="Re-uses this same plan for recurring collection">
              <Segmented label="Refresh mode" value={draft.refresh.mode as "manual" | "scheduled" | "watch"} onChange={(mode) => patch({ refresh: { ...draft.refresh, mode } })}
                options={[{ value: "manual", label: "Manual" }, { value: "scheduled", label: "Scheduled" }, { value: "watch", label: "Watch" }]} />
              <NumberField label="Refresh every (hours)" value={draft.refresh.interval_hours} min={1} max={2160} onChange={(v) => patch({ refresh: { ...draft.refresh, interval_hours: v } })} hint="Scheduling is stored with the plan; runs start from Refresh sources." />
              <label className="check-row"><input type="checkbox" checked={draft.refresh.change_detection} onChange={(event) => patch({ refresh: { ...draft.refresh, change_detection: event.target.checked } })} /><span>Flag new and changed items on refresh</span></label>
            </Collapsible>
            <Collapsible title="Plan data" hint="The structured plan behind this page">
              {Object.keys(draft.extra).length > 0 && <dl className="kv">{Object.entries(draft.extra).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></div>)}</dl>}
              <pre className="json-view">{JSON.stringify({ ...draft, queries: `(${draft.queries.length} queries)` }, null, 2)}</pre>
            </Collapsible>
          </div>}
        </div>
        {error && <div className="inline-error" role="alert">{error}</div>}
        <footer className="modal-foot">
          <span className="muted">{dirty ? "Unsaved edits" : "No changes"}</span>
          <div><button className="button button-quiet" onClick={onCancel}>Cancel</button>
            <button className="button button-primary" disabled={saving || !draft.topic.trim()} onClick={() => onSave(draft)}>{saving ? "Saving…" : "Save plan"}</button></div>
        </footer>
      </section>
    </div>
  );
}

