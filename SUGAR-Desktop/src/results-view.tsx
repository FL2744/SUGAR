import { useCallback, useEffect, useMemo, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { downloadWorkspaceFile } from "./bridge";
import { research } from "./research-api";
import type { BriefResult, ResultItem, ResultsPayload, RunSummary, ThemeRow, Verdict } from "./research-types";
import type { Prefs } from "./prefs";
import { ItemInspector } from "./item-inspector";
import { CopyButton, EmptyState, IncompleteNotice, Pill, Segmented, Spinner, StatusPill, VERDICTS, VerdictPill, languageName, platformLabel, relativeTime, titleCase } from "./ui";

type TextMode = "original" | "translation" | "both";
const GROUPS = [["none", "No grouping"], ["platform", "Platform"], ["language", "Language"], ["geography", "Geography"], ["query", "Search query"], ["author", "Author"]] as const;

function ItemRow({ item, mode, onInspect, onReview }: { item: ResultItem; mode: TextMode; onInspect: () => void; onReview: (verdict: Verdict) => void }) {
  const translated = item.translated_text;
  const showTranslation = mode !== "original" && translated;
  return (
    <li className={`result-row ${item.status === "duplicate" ? "is-duplicate" : ""}`}>
      <div className="result-meta">
        <Pill tone="info">{platformLabel(item.platform)}</Pill>
        <span className="result-author">{item.author || "unknown"}</span>
        <span className="muted">{item.published_at ? item.published_at.slice(0, 10) : ""}</span>
        <Pill>{languageName(item.language || "und")}</Pill>
        {item.status === "duplicate" && <Pill tone="warn" title={`Similar to ${item.duplicate_of}`}>Duplicate · {Math.round(item.similarity * 100)}%</Pill>}
        {item.status === "excluded" && <Pill tone="warn">Excluded</Pill>}
        {item.status === "rejected" && <Pill tone="warn" title={item.rejection_reason}>Rejected</Pill>}
        {item.is_new && item.known_from_run === "" && <span className="new-dot" title="Not seen in an earlier run" />}
        {item.geography.slice(0, 2).map((g) => <Pill key={g} tone="neutral">{g}</Pill>)}
        {item.relevance && item.relevance.band !== "likely" && <Pill tone={item.relevance.band === "unlikely" ? "warn" : "neutral"} title={item.relevance.reasons.join("; ")}>{item.relevance.band === "unlikely" ? "Likely off topic" : "Relevance unsure"}</Pill>}
        <VerdictPill verdict={item.review?.verdict || ""} />
        {(item.review?.tags || []).slice(0, 3).map((t) => <span key={t} className="tag-chip">#{t}</span>)}
        {(item.review?.comments || 0) > 0 && <span className="muted" title="Comments on this item">💬 {item.review?.comments}</span>}
      </div>
      {mode === "both" && translated ? (
        <div className="result-both"><p dir="auto">{item.original_text}</p><p dir="auto" className="translated">{translated}</p></div>
      ) : (
        <p className="result-text" dir="auto">{showTranslation ? translated : item.original_text}</p>
      )}
      {mode === "translation" && !translated && item.language !== "en" && <small className="muted">Not translated{item.translation_status ? ` (${item.translation_status})` : ""}</small>}
      <div className="item-actions">
        {item.url && <a className="text-button" href={item.url} target="_blank" rel="noreferrer">Open source ↗</a>}
        <button className="text-button" onClick={onInspect}>Provenance</button>
        <span className="triage" role="group" aria-label="Review this item">
          {VERDICTS.map((v) => <button key={v.id} type="button" className={`triage-btn ${item.review?.verdict === v.id ? "on" : ""}`} aria-pressed={item.review?.verdict === v.id}
            onClick={() => onReview(item.review?.verdict === v.id ? "" : v.id)} title={v.label}><span aria-hidden="true">{v.mark}</span> {v.label}</button>)}
        </span>
        <small className="muted">query: {item.query}</small>
      </div>
    </li>
  );
}

export function ResultsView({ projectId, runId, runs, prefs, author, onSelectRun, onOpenActivity, onOpenResearch, onRunStarted, onError, projectPath }: {
  projectId: string; runId: string; runs: RunSummary[]; prefs: Prefs; author: string; projectPath: string;
  onSelectRun: (runId: string) => void; onOpenActivity: (runId: string) => void; onOpenResearch: () => void;
  onRunStarted: (projectId: string, run: RunSummary) => void; onError: (message: string) => void;
}) {
  const [data, setData] = useState<ResultsPayload | null>(null);
  const [run, setRun] = useState<RunSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [group, setGroup] = useState<(typeof GROUPS)[number][0]>("platform");
  const [platform, setPlatform] = useState("");
  const [language, setLanguage] = useState("");
  const [geography, setGeography] = useState("");
  const [status, setStatus] = useState("accepted");
  const [translated, setTranslated] = useState("");
  const [verdictFilter, setVerdictFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [relFilter, setRelFilter] = useState("");
  const [newOnly, setNewOnly] = useState(false);
  const [mode, setMode] = useState<TextMode>("original");
  const [inspect, setInspect] = useState("");
  const [exportInfo, setExportInfo] = useState<{ archive: string; directory: string; files: string[] } | null>(null);
  const [busy, setBusy] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const advanced = prefs.mode === "advanced";

  const load = useCallback(async () => {
    if (!projectId || !runId) return;
    setLoading(true);
    try {
      const [payload, summary] = await Promise.all([
        research.results(projectId, runId, { group_by: group, q, platform, language, geography, status, translated, verdict: verdictFilter, tag: tagFilter, relevance: relFilter, new_only: newOnly, limit: 300 }),
        research.run(projectId, runId),
      ]);
      setData(payload); setRun(summary);
    } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setLoading(false); }
  }, [projectId, runId, group, q, platform, language, geography, status, translated, verdictFilter, tagFilter, relFilter, newOnly, onError]);

  useEffect(() => { const timer = window.setTimeout(() => void load(), q ? 250 : 0); return () => window.clearTimeout(timer); }, [load, q]);
  useEffect(() => { setExportInfo(null); }, [runId]);

  const facets = data?.facets;
  const hasTranslations = useMemo(() => Boolean(facets?.languages.some((l) => l.key !== "en" && l.key !== "und")), [facets]);

  // Judge an item from the list. The row updates in place; filters and counts refresh from the server's answer.
  const reviewItem = async (item: ResultItem, verdict: Verdict) => {
    try {
      const result = await research.postReview(projectId, item.item_id, { kind: "verdict", verdict }, author);
      setData((current) => {
        if (!current) return current;
        const patch = (row: ResultItem) => row.item_id === item.item_id ? { ...row, review: { verdict: result.review.verdict, tags: result.review.tags, comments: result.review.comments.length } } : row;
        return { ...current, review: result.summary, items: current.items.map(patch), groups: current.groups.map((g) => ({ ...g, items: g.items.map(patch) })) };
      });
    } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); }
  };

  const [codingNote, setCodingNote] = useState("");
  const codeRun = async (mode: "auto" | "deterministic") => {
    setBusy("coding"); setCodingNote("");
    try {
      const r = await research.runCoding(projectId, runId, mode);
      setCodingNote(`Proposed ${r.proposed} labels across ${r.with_codes} of ${r.items} items${r.model_used ? " (patterns and your AI model)" : " (patterns)"}. Open an item's Provenance to confirm or reject them.${r.warnings.length ? " " + r.warnings[0] : ""}`);
    } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };

  const [themes, setThemes] = useState<{ themes: ThemeRow[]; note: string } | null>(null);
  const [brief, setBrief] = useState<BriefResult | null>(null);
  const scoreRun = async () => {
    setBusy("relevance"); setCodingNote("");
    try {
      const r = await research.scoreRelevance(projectId, runId, "auto");
      setCodingNote(`Scored ${r.scored} items: ${r.bands.likely} likely relevant, ${r.bands.uncertain} unsure, ${r.bands.unlikely} likely off topic${r.model_used ? ` (your AI model re-checked ${r.model_refined})` : ""}. Nothing was removed.${r.warnings.length ? " " + r.warnings[0] : ""}`);
      await load();
    } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };
  const markUnlikely = async () => {
    if (!window.confirm(`Mark the ${data?.relevance_bands?.unlikely ?? 0} items that look off topic as “not relevant”? You can change any of them afterward.`)) return;
    setBusy("unlikely");
    try { const r = await research.applyUnlikely(projectId, runId, author); setCodingNote(`Marked ${r.marked} items not relevant${r.skipped_already_reviewed ? `; ${r.skipped_already_reviewed} already had a verdict and were left alone` : ""}.`); await load(); }
    catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };
  const showThemes = async () => { setBusy("themes"); try { setThemes(await research.themes(projectId, runId)); } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); } };
  const makeBrief = async (mode: "deterministic" | "auto") => {
    setBusy("brief"); setBrief(null);
    try { setBrief(await research.brief(projectId, runId, mode)); } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };

  const exportRun = async () => {
    setBusy("export");
    try { setExportInfo(await research.exportRun(projectId, runId)); }
    catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };
  const download = async (relative: string, name: string) => {
    try { await downloadWorkspaceFile(`sugar-file://${projectId}/${relative}`, name); } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); }
  };
  const operate = async (kind: string) => {
    setBusy(kind);
    try { onRunStarted(projectId, await research.startRun(projectId, { kind, parent_run_id: runId, debug: prefs.debug })); }
    catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };

  if (!projectId || runs.length === 0) return (
    <section className="page-content"><EmptyState icon="▤" title="No results yet" action={<button className="button button-primary" onClick={onOpenResearch}>Start a research request</button>}>
      Collected items appear here with their sources, languages, translations, and provenance.</EmptyState></section>);

  const selected = runs.find((r) => r.run_id === runId);
  const renderItems = (items: ResultItem[]) => <ul className="result-list">{items.map((item) => <ItemRow key={item.item_id + item.run_id} item={item} mode={mode} onInspect={() => setInspect(item.item_id)} onReview={(v) => void reviewItem(item, v)} />)}</ul>;

  return (
    <section className="page-content results-page">
      <div className="page-heading compact-heading">
        <div><div className="eyebrow">RESULTS <span className="eyebrow-line" /></div><h1>{run?.plan?.topic ? titleCase(run.plan.topic) : "Results"}</h1>
          <p>{data ? `${data.total} item${data.total === 1 ? "" : "s"} shown of ${data.all_items} collected` : "Loading…"}{run ? ` · ${titleCase(run.kind)} ${relativeTime(run.finished_at || run.created_at)}` : ""}</p></div>
        <div className="run-controls">
          <label className="select-inline"><span className="sr-only">Run</span>
            <select value={runId} onChange={(event) => onSelectRun(event.target.value)} aria-label="Choose run">
              {runs.map((r) => <option key={r.run_id} value={r.run_id}>{titleCase(r.kind)} · {relativeTime(r.finished_at || r.created_at)} · {r.counts?.collected ?? 0} items</option>)}
            </select></label>
          {selected && <StatusPill status={selected.status} />}
          <button className="button button-secondary" onClick={() => onOpenActivity(runId)}>Activity</button>
          <button className="button button-primary" disabled={busy === "export"} onClick={() => void exportRun()}>{busy === "export" ? <Spinner /> : "Export"}</button>
        </div>
      </div>

      {run?.completeness && !run.completeness.complete && <IncompleteNotice run={run} />}
      {run?.status === "cancelled" && <div className="notice notice-info">This run was cancelled; results collected before that are shown.</div>}

      {exportInfo && (
        <div className="notice notice-ok export-box"><strong>Export ready.</strong> Stored in the project at <code>{exportInfo.directory}</code>{isTauri() && projectPath ? <> (<code>{projectPath}</code>)</> : null}
          <div className="export-files">
            {!isTauri() && <>
              <button className="button button-secondary button-small" onClick={() => void download(exportInfo.archive, `${runId}.zip`)}>Bundle (.zip)</button>
              {["results.csv", "corpus.jsonl", "report.md", "run-manifest.json", "plan.json", "translations.jsonl", "activity-log.jsonl", "sources.csv"].filter((f) => exportInfo.files.includes(f)).map((f) => (
                <button key={f} className="button button-quiet button-small" onClick={() => void download(`${exportInfo.directory}/${f}`, f)}>{f}</button>))}
            </>}
            {isTauri() && <CopyButton text={projectPath ? `${projectPath}/${exportInfo.directory}` : exportInfo.directory} label="Copy folder path" />}
          </div></div>)}

      <div className="toolbar results-toolbar">
        <div className="search-field"><span aria-hidden="true">⌕</span><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Search text, author, or link" aria-label="Search results" /></div>
        <select value={group} onChange={(event) => setGroup(event.target.value as typeof group)} aria-label="Group by">{GROUPS.map(([id, label]) => <option key={id} value={id}>{id === "none" ? label : `Group by ${label.toLowerCase()}`}</option>)}</select>
        <select value={platform} onChange={(event) => setPlatform(event.target.value)} aria-label="Platform"><option value="">All platforms</option>{facets?.platforms.map((f) => <option key={f.key} value={f.key}>{platformLabel(f.key)} ({f.count})</option>)}</select>
        <select value={language} onChange={(event) => setLanguage(event.target.value)} aria-label="Language"><option value="">All languages</option>{facets?.languages.map((f) => <option key={f.key} value={f.key}>{languageName(f.key)} ({f.count})</option>)}</select>
        {(advanced || (facets?.geographies.length || 0) > 1) && <select value={geography} onChange={(event) => setGeography(event.target.value)} aria-label="Geography"><option value="">Everywhere</option>{facets?.geographies.map((f) => <option key={f.key} value={f.key}>{f.key} ({f.count})</option>)}</select>}
        {advanced && <select value={translated} onChange={(event) => setTranslated(event.target.value)} aria-label="Translation"><option value="">Any translation state</option><option value="yes">Translated</option><option value="no">Not translated</option></select>}
        {advanced && <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Status"><option value="accepted">Kept</option><option value="duplicate">Duplicates ({data?.duplicates ?? 0})</option><option value="rejected">Rejected ({data?.rejected ?? 0})</option><option value="excluded">Excluded ({data?.excluded ?? 0})</option><option value="all">Everything</option></select>}
        <select value={verdictFilter} onChange={(event) => setVerdictFilter(event.target.value)} aria-label="Review status"><option value="">Any review status</option><option value="unreviewed">Not yet reviewed</option>{VERDICTS.map((v) => <option key={v.id} value={v.id}>{v.label} ({data?.review?.verdicts[v.id] ?? 0})</option>)}</select>
        {Object.keys(data?.review?.tags || {}).length > 0 && <select value={tagFilter} onChange={(event) => setTagFilter(event.target.value)} aria-label="Tag"><option value="">Any tag</option>{Object.entries(data?.review?.tags || {}).map(([t, n]) => <option key={t} value={t}>#{t} ({n})</option>)}</select>}
        {(data?.relevance_bands?.unscored ?? 1) < (data?.all_items ?? 0) && <select value={relFilter} onChange={(event) => setRelFilter(event.target.value)} aria-label="Relevance"><option value="">Any relevance</option><option value="likely">Likely relevant ({data?.relevance_bands?.likely ?? 0})</option><option value="uncertain">Unsure ({data?.relevance_bands?.uncertain ?? 0})</option><option value="unlikely">Likely off topic ({data?.relevance_bands?.unlikely ?? 0})</option></select>}
        {run?.kind === "refresh_sources" && <label className="check-row"><input type="checkbox" checked={newOnly} onChange={(event) => setNewOnly(event.target.checked)} /><span>New since last run</span></label>}
        {(hasTranslations || mode !== "original") && <Segmented label="Text shown" value={mode} onChange={setMode} options={[{ value: "original", label: "Original" }, { value: "translation", label: "Translated" }, { value: "both", label: "Side by side" }]} />}
      </div>

      {data?.review && data.all_items > 0 && (
        <div className="review-progress" role="status" aria-label="Review progress">
          <div className="review-bar" aria-hidden="true"><i style={{ width: `${Math.min(100, Math.round((data.review.reviewed / data.all_items) * 100))}%` }} /></div>
          <span><strong>{data.review.reviewed}</strong> of {data.all_items} reviewed · {data.review.verdicts.relevant ?? 0} relevant · {data.review.verdicts.follow_up ?? 0} to follow up{data.review.commented ? ` · ${data.review.commented} discussed` : ""}</span>
        </div>)}

      {loading && !data && <div className="loading-block"><Spinner /> Loading results…</div>}
      {data && data.total === 0 && <EmptyState icon="∅" title="Nothing matches">{data.all_items === 0 ? "This run did not keep any items. Check the Activity view for warnings." : "Try clearing a filter."}</EmptyState>}
      {data && group === "none" && data.items.length > 0 && renderItems(data.items)}
      {data && group !== "none" && data.groups.map((g) => (
        <section className="result-group" key={g.key}>
          <button className="group-head" aria-expanded={!collapsed[g.key]} onClick={() => setCollapsed({ ...collapsed, [g.key]: !collapsed[g.key] })}>
            <span aria-hidden="true">{collapsed[g.key] ? "▸" : "▾"}</span><strong>{group === "platform" ? platformLabel(g.key) : group === "language" ? languageName(g.key) : g.key}</strong><span className="group-count">{g.count}</span></button>
          {!collapsed[g.key] && renderItems(g.items)}
          {!collapsed[g.key] && g.count > g.items.length && <p className="muted small-pad">Showing {g.items.length} of {g.count}. Narrow the filters or export the run to see everything.</p>}
        </section>))}

      <section className="panel ops-panel">
        <h3>Do more with this run</h3>
        <div className="ops-row">
          <button className="button button-secondary" disabled={Boolean(busy)} onClick={() => void operate("rerun")} title="Execute the same plan again">Rerun</button>
          <button className="button button-secondary" disabled={Boolean(busy)} onClick={() => void operate("refresh_sources")} title="Search again; flag new and changed items">Refresh sources</button>
          <button className="button button-secondary" disabled={Boolean(busy)} onClick={() => void operate("reprocess")} title="Repeat translation and extraction without collecting again">Reprocess results</button>
          <button className="button button-secondary" disabled={Boolean(busy)} onClick={() => void codeRun("auto")} title="Propose audiences, programs and reported attendance from each item, with quotes. You confirm them.">Code activity and audiences</button>
          <button className="button button-secondary" disabled={Boolean(busy)} onClick={() => void scoreRun()} title="Give each item a relevance score with its reasons. Nothing is removed.">Check relevance</button>
          {(data?.relevance_bands?.unlikely ?? 0) > 0 && <button className="button button-quiet" disabled={Boolean(busy)} onClick={() => void markUnlikely()}>Mark {data?.relevance_bands?.unlikely} likely off-topic items…</button>}
          <button className="button button-secondary" disabled={Boolean(busy)} onClick={() => void showThemes()}>Show themes</button>
          <button className="button button-primary" disabled={Boolean(busy)} onClick={() => void makeBrief("deterministic")} title="A written brief with numbered sources, coverage limits and method">{busy === "brief" ? <Spinner /> : "Create brief"}</button>
          <button className="button button-quiet" onClick={onOpenResearch}>Rebuild plan or reinterpret request…</button>
        </div>
        {codingNote && <div className="notice notice-info" role="status">{codingNote}</div>}
        {themes && <div className="theme-box"><h4>What the items are about</h4>{themes.themes.length === 0 ? <p className="muted">{themes.note}</p> : <ul className="theme-list">{themes.themes.map((t) => <li key={t.key}><strong>{t.label}</strong> <small className="muted">{t.count} items · {Math.round(t.share * 100)}%</small>{t.examples[0] && <q dir="auto">{t.examples[0].text}</q>}</li>)}</ul>}<small className="muted">{themes.note}</small></div>}
        {brief && <div className="notice notice-ok export-box" role="status"><strong>Brief ready.</strong> {brief.references.length} numbered sources{brief.model_summary ? ", with a model-assisted summary" : ""}.{brief.warnings.map((w) => <span key={w}> {w}</span>)}
          <div className="export-files"><button className="button button-secondary button-small" onClick={() => void download(brief.files.docx, "research-brief.docx")}>Word (.docx)</button><button className="button button-secondary button-small" onClick={() => void download(brief.files.markdown, "research-brief.md")}>Markdown</button>
            <button className="button button-quiet button-small" onClick={() => void makeBrief("auto")} title="Adds a short summary written by your AI model; every sentence must cite a source">Add model-assisted summary</button></div>
          <details><summary>Preview</summary><pre className="brief-preview">{brief.markdown}</pre></details></div>}
        <p className="muted">Each of these does exactly one thing. See the Research page for details.</p>
      </section>
      {inspect && <ItemInspector projectId={projectId} runId={runId} itemId={inspect} author={author} onClose={() => setInspect("")} />}
    </section>
  );
}
