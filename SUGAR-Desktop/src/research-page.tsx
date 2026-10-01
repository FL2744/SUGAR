import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { research } from "./research-api";
import type { Interpretation, PlanSpec, PlatformRow, ProjectOverview, ProviderProfileRow, RunSummary, SummaryRow } from "./research-types";
import type { Prefs } from "./prefs";
import { PlanEditor } from "./plan-editor";
import { ChipInput, Collapsible, Pill, Segmented, Spinner, StatusPill, languageName, relativeTime } from "./ui";

const EXAMPLES = [
  "Search democracy in the Middle East on all platforms.",
  "What are people saying about climate policy in Brazil on Bluesky since 2023?",
  "Look into protests in Iran over the last 6 months, in Persian and English.",
  "Quick look at education reform in Kenya, excluding sports.",
];

type Props = {
  prefill?: { text: string; n: number };
  projectId: string;
  projectName: string;
  prefs: Prefs;
  overview: ProjectOverview | null;
  onOverview: () => Promise<void> | void;
  ensureProject: (suggestedName: string) => Promise<string>;
  onRunStarted: (projectId: string, run: RunSummary) => void;
  onOpenSettings: () => void;
  onOpenResults: (runId: string) => void;
  onError: (message: string) => void;
};

const OPERATIONS = [
  { id: "reinterpret", label: "Reinterpret request", detail: "Run the natural-language interpretation again on the stored request. Shows a new plan for you to accept." },
  { id: "rebuild", label: "Rebuild plan", detail: "Generate a fresh set of searches from the requirement. Queries you added yourself are kept." },
  { id: "refresh_sources", label: "Refresh sources", detail: "Search again for newer or changed material. New, known and changed items are flagged." },
  { id: "reprocess", label: "Reprocess results", detail: "Repeat translation and extraction on the last run's items without collecting anything again." },
  { id: "rerun", label: "Rerun", detail: "Execute the previous plan again exactly as it was recorded, including edits." },
] as const;

/** Sites and feeds you name: institution websites, ministry and embassy pages, news feeds. Saved per project; used on the next run. */
function FeedsCard({ projectId, saved, savedSites, onSaved, onError }: { projectId: string; saved: string[]; savedSites: string[]; onSaved: () => void; onError: (m: string) => void }) {
  const [feeds, setFeeds] = useState(saved.join("\n"));
  const [sites, setSites] = useState(savedSites.join("\n"));
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  useEffect(() => { setFeeds(saved.join("\n")); }, [saved]);
  useEffect(() => { setSites(savedSites.join("\n")); }, [savedSites]);
  const save = async () => {
    setBusy(true); setDone(false);
    try { await research.saveSettings(projectId, { rss_feeds: feeds.split(/\s+/).filter(Boolean), web_seeds: sites.split(/\s+/).filter(Boolean) }); setDone(true); onSaved(); }
    catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(false); }
  };
  const count = saved.length + savedSites.length;
  return (
    <Collapsible title="Your own sources (optional)" hint={count ? `${savedSites.length} website${savedSites.length === 1 ? "" : "s"}, ${saved.length} feed${saved.length === 1 ? "" : "s"} included in runs` : "Add institution websites and news feeds to read"}>
      <label className="field-block"><span>Websites to read, one per line</span>
        <textarea rows={3} value={sites} onChange={(event) => { setSites(event.target.value); setDone(false); }} placeholder="https://example.org/" spellCheck={false} /></label>
      <label className="field-block"><span>News and institution feeds (RSS/Atom), one per line</span>
        <textarea rows={3} value={feeds} onChange={(event) => { setFeeds(event.target.value); setDone(false); }} placeholder="https://example.org/news/feed.xml" spellCheck={false} /></label>
      <p className="footnote">Pages and feed entries that mention your search are collected, along with the news and event pages a site links to. SUGAR follows each site's robots.txt, reads one page per second, and only public web addresses. Wikipedia, news coverage (GDELT) and scholarly works (OpenAlex) are searched automatically.</p>
      <div className="preview-actions"><button type="button" className="button button-secondary" onClick={() => void save()} disabled={busy}>{busy ? <><Spinner /> Saving…</> : "Save sources"}</button>{done && <span className="muted" role="status">Saved — used on the next run.</span>}</div>
    </Collapsible>
  );
}

function providerState(p: ProviderProfileRow): { mark: string; text: string } {
  if (!p.has_credential && p.type !== "local") return { mark: "⚠", text: "key missing" };
  if (p.status.state === "ok") return { mark: "✓", text: "connected" };
  if (p.status.state === "failed") return { mark: "✕", text: "last test failed" };
  return { mark: "•", text: "not tested" };
}

/** One explicit place to pick which AI SUGAR uses (e.g. OpenAI or Virginia Tech ARC), or none at all. */
function ProviderChooser({ providers, types, value, onChange, onOpenSettings }: {
  providers: ProviderProfileRow[]; types: Record<string, string>; value: string; onChange: (id: string) => void; onOpenSettings: () => void;
}) {
  const current = providers.find((p) => p.id === value);
  const state = current ? providerState(current) : null;
  return (
    <div className="provider-chooser">
      <label className="field-block"><span>AI model</span>
        <select value={value} onChange={(event) => onChange(event.target.value)} aria-label="AI model for interpretation and translation">
          {providers.map((p) => { const st = providerState(p); return <option key={p.id} value={p.id}>{p.name} · {types[p.type] || p.type} · {p.effective_model || "no model"} ({st.text})</option>; })}
          <option value="none">No AI — built-in only</option>
        </select></label>
      {value === "none"
        ? <small className="muted">Built-in interpreter only. Non-English posts will not be translated.</small>
        : state && state.mark !== "✓" ? <small className="warn-text">{state.mark} {current?.name}: {state.text}. <button type="button" className="text-button" onClick={onOpenSettings}>Open Settings</button></small> : null}
    </div>
  );
}

export function PlanPreview({ summary, interpretation, plan, onRun, onEdit, onAdvanced, running, canRun, onOpenSettings, advanced }: {
  summary: SummaryRow[]; interpretation: Interpretation | null; plan: PlanSpec; onRun: () => void; onEdit: () => void; onAdvanced: () => void;
  running: boolean; canRun: boolean; onOpenSettings: () => void; advanced: boolean;
}) {
  const method = interpretation?.method;
  const enabled = plan.queries.filter((q) => q.enabled);
  const card = useRef<HTMLElement>(null);
  // A fresh interpretation lands below the request box; bring it into view so the next step is never off-screen.
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    card.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "nearest" });
  }, [interpretation]);
  return (
    <section ref={card} className="panel plan-preview-card" aria-label="Interpreted research plan">
      <div className="panel-heading">
        <div><span className="eyebrow">HERE IS WHAT SUGAR UNDERSTOOD</span><h3>Research plan</h3></div>
        <div className="pill-row">
          {method === "llm" && <Pill tone="info" title={interpretation?.provider?.model}>Interpreted by {interpretation?.provider?.name || "your model"}</Pill>}
          {method === "deterministic" && <Pill tone="neutral">Built-in interpreter</Pill>}
          {method === "manual" && <Pill tone="neutral">Entered manually</Pill>}
          {interpretation && interpretation.confidence > 0 && interpretation.confidence < 0.7 && <Pill tone="warn">Low confidence — please check</Pill>}
        </div>
      </div>
      <dl className="summary-grid">
        {summary.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}
      </dl>
      {interpretation && interpretation.assumptions.length > 0 && (
        <div className="assumptions"><strong>Assumed for you</strong><ul>{interpretation.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></div>
      )}
      {interpretation?.issues.filter((i) => i.severity === "warning").map((issue) => (
        <div className="notice notice-warn" key={issue.field + issue.message}>
          {issue.message}
          {issue.field === "provider" || issue.field === "interpretation" ? <button className="text-button" onClick={onOpenSettings}>Open Settings → LLM Providers</button> : null}
        </div>))}
      <Collapsible title={`Planned searches (${enabled.length})`} hint="What will actually be sent to each platform" defaultOpen={advanced}>
        <ul className="query-list">
          {plan.queries.map((q) => (
            <li key={q.id} className={q.enabled ? "" : "off"}>
              <code>{q.text}</code>
              <span className="muted">{[q.platform && `only ${q.platform}`, q.language && languageName(q.language), q.origin].filter(Boolean).join(" · ")}</span>
              {!q.enabled && <small>disabled</small>}
              {q.rationale && <small>{q.rationale}</small>}
            </li>))}
        </ul>
      </Collapsible>
      <div className="preview-actions">
        <button className="button button-primary" onClick={onRun} disabled={running || !canRun}>{running ? <><Spinner /> Starting…</> : <>Run now <span aria-hidden="true">→</span></>}</button>
        <button className="button button-secondary" onClick={onEdit} disabled={running}>Edit plan</button>
        <button className="button button-quiet" onClick={onAdvanced} disabled={running}>Advanced configuration</button>
      </div>
    </section>
  );
}

function ManualEntry({ initial, platforms, onSubmit, busy }: { initial: string; platforms: PlatformRow[]; onSubmit: (fields: Record<string, unknown>) => void; busy: boolean }) {
  const [topic, setTopic] = useState("");
  const [geography, setGeography] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [languages, setLanguages] = useState<string[]>([]);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [depth, setDepth] = useState<"quick" | "standard" | "deep">("standard");
  return (
    <section className="panel manual-entry" aria-label="Enter the research plan manually">
      <div className="panel-heading"><div><span className="eyebrow">MANUAL ENTRY</span><h3>Tell SUGAR what to research</h3></div></div>
      <p className="muted">SUGAR could not work out the topic from “{initial || "your request"}”. Fill in the fields below — the same validation applies.</p>
      <div className="form-stack">
        <label className="field-block"><span>Research topic <em>Required</em></span><input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="e.g. democracy" autoFocus /></label>
        <ChipInput label="Regions" values={geography} onChange={setGeography} placeholder="Add a country or region, then press Enter" />
        <div className="field-block"><span>Platforms</span>
          <div className="check-grid">{platforms.filter((p) => p.keyword_search).map((p) => (
            <label key={p.id} className="check-row"><input type="checkbox" checked={selected.includes(p.id)} onChange={() => setSelected(selected.includes(p.id) ? selected.filter((x) => x !== p.id) : [...selected, p.id])} /><span>{p.label}</span></label>))}</div>
          <small>{selected.length ? "Only the checked platforms." : "None checked: all enabled platforms."}</small>
        </div>
        <ChipInput label="Languages" values={languages} onChange={setLanguages} placeholder="Automatic — add a code such as ar" />
        <div className="field-grid"><label className="field-block"><span>From</span><input type="date" value={start} onChange={(event) => setStart(event.target.value)} /></label>
          <label className="field-block"><span>Until</span><input type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></label></div>
        <Segmented label="Depth" value={depth} onChange={setDepth} options={[{ value: "quick", label: "Quick" }, { value: "standard", label: "Standard" }, { value: "deep", label: "Deep" }]} />
        <div><button className="button button-primary" disabled={!topic.trim() || busy} onClick={() => onSubmit({
          topic, geography, platforms: selected, source_scope: selected.length ? "selected" : "all_enabled", languages: languages.length ? languages : ["auto"],
          timeframe: { start, end, label: "" }, depth, research_question: initial })}>Use these settings</button></div>
      </div>
    </section>
  );
}

export function ResearchPage({ projectId, projectName, prefs, overview, onOverview, ensureProject, onRunStarted, onOpenSettings, onOpenResults, onError, prefill }: Props) {
  const [text, setText] = useState("");
  useEffect(() => { if (prefill?.text) setText(prefill.text); }, [prefill]);
  const [interpretation, setInterpretation] = useState<Interpretation | null>(null);
  const [plan, setPlan] = useState<PlanSpec | null>(null);
  const [summary, setSummary] = useState<SummaryRow[]>([]);
  const [busy, setBusy] = useState("");
  const [editing, setEditing] = useState<"" | "basic" | "advanced">("");
  const [saveError, setSaveError] = useState("");
  const [platforms, setPlatforms] = useState<PlatformRow[]>([]);
  const [providers, setProviders] = useState<ProviderProfileRow[]>([]);
  const [providerTypes, setProviderTypes] = useState<Record<string, string>>({});
  const [defaultProvider, setDefaultProvider] = useState("");
  const [providerChoice, setProviderChoice] = useState(() => { try { return localStorage.getItem("sugar.providerChoice") || ""; } catch { return ""; } });
  const [proposal, setProposal] = useState<{ kind: string; interp: Interpretation } | null>(null);
  const advanced = prefs.mode === "advanced";

  useEffect(() => {
    void research.platforms().then(setPlatforms).catch(() => undefined);
    void research.providers().then((r) => {
      setProviders(r.profiles); setDefaultProvider(r.default_profile_id);
      setProviderTypes(Object.fromEntries(r.types.map((t) => [t.id, t.label])));
    }).catch(() => undefined);
  }, []);
  // The model SUGAR will use: the saved choice if it still exists, otherwise the default provider, otherwise no AI.
  const chosenProvider = providerChoice === "none" ? "none"
    : providers.some((p) => p.id === providerChoice) ? providerChoice : (defaultProvider || (providers[0]?.id ?? "none"));
  const chooseProvider = (id: string) => {
    setProviderChoice(id);
    try { localStorage.setItem("sugar.providerChoice", id); } catch { /* storage may be unavailable */ }
    setPlan((current) => current ? { ...current, provider: { ...current.provider, profile_id: id, use_for_planning: id !== "none" } } : current);
  };
  useEffect(() => {
    if (overview && !plan && !interpretation) {
      setText(overview.requirement_text || "");
    }
  }, [overview, plan, interpretation]);

  const storedPlan = overview?.plan || null;
  const lastRun = overview?.runs?.[0];
  const canOperate = Boolean(projectId && storedPlan);

  const interpret = useCallback(async () => {
    if (!text.trim()) return;
    setBusy("interpret"); setSaveError(""); setProposal(null);
    try {
      const result = await research.interpret(text.trim(), prefs.interpreter, projectId, chosenProvider);
      setInterpretation(result);
      setPlan(result.plan);
      setSummary(result.summary);
    } catch (issue) {
      onError(issue instanceof Error ? issue.message : String(issue));
    } finally { setBusy(""); }
  }, [text, prefs.interpreter, projectId, chosenProvider, onError]);

  const submitManual = async (fields: Record<string, unknown>) => {
    setBusy("manual");
    try {
      const result = await research.manualPlan(fields);
      if (!result.plan) { onError(result.issues.map((i) => i.message).join(" ") || "The plan is not valid."); return; }
      setInterpretation((current) => current ? { ...current, method: "manual", needs_manual_entry: false, plan: result.plan, summary: result.summary, clarifications: [], assumptions: [] } : current);
      setPlan(result.plan); setSummary(result.summary);
    } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };

  const persistPlan = async (target: PlanSpec, reason: string, id?: string) => {
    const project = id || await ensureProject(target.topic || "New research project");
    const saved = await research.savePlan(project, target, reason, text.trim() || overview?.requirement_text || "");
    return { project, saved };
  };

  const runNow = async () => {
    if (!plan) return;
    setBusy("run");
    try {
      const { project, saved } = await persistPlan(plan, interpretation?.method === "manual" ? "manual" : "interpreted", projectId || undefined);
      const run = await research.startRun(project, { plan: saved.plan, debug: prefs.debug });
      await onOverview();
      onRunStarted(project, run);
      setInterpretation(null); setPlan(null);
    } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };

  const saveEdited = async (edited: PlanSpec) => {
    setBusy("save"); setSaveError("");
    try {
      const normalized = await research.normalizePlan(edited);
      if (interpretation || !projectId) {
        setPlan(normalized.plan); setSummary(normalized.summary);
      } else {
        const { saved } = await persistPlan(normalized.plan, "edited", projectId);
        setPlan(saved.plan); setSummary(saved.summary);
        await onOverview();
      }
      setEditing("");
    } catch (issue) { setSaveError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };

  const operate = async (id: (typeof OPERATIONS)[number]["id"]) => {
    if (!projectId) return;
    setBusy(id);
    try {
      if (id === "reinterpret" || id === "rebuild") {
        const interp = id === "reinterpret" ? await research.reinterpret(projectId, prefs.interpreter) : await research.rebuildPlan(projectId);
        setProposal({ kind: id, interp });
      } else {
        const run = await research.startRun(projectId, { kind: id, debug: prefs.debug });
        await onOverview();
        onRunStarted(projectId, run);
      }
    } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };

  const acceptProposal = async () => {
    if (!proposal?.interp.plan || !projectId) return;
    setBusy("accept");
    try {
      await research.savePlan(projectId, proposal.interp.plan, proposal.kind === "reinterpret" ? "reinterpreted" : "rebuilt", proposal.interp.request || overview?.requirement_text || "");
      setProposal(null);
      await onOverview();
    } catch (issue) { onError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };

  const noProvider = providers.length === 0;
  const placeholder = useMemo(() => EXAMPLES[Math.floor(Date.now() / 60000) % EXAMPLES.length], []);

  return (
    <section className="page-content research-page">
      <div className="page-heading compact-heading"><div><div className="eyebrow">RESEARCH <span className="eyebrow-line" /></div>
        <h1>What would you like to research?</h1><p>Describe it in your own words. SUGAR turns it into a plan you can check before anything runs.</p></div>
        {projectId && <Pill tone="info" title="The current project">Project · {projectName}</Pill>}
      </div>

      <form className="panel request-card" onSubmit={(event) => { event.preventDefault(); void interpret(); }}>
        <label className="field-block"><span className="sr-only">Research request</span>
          <textarea className="request-box" value={text} rows={3} onChange={(event) => setText(event.target.value)} placeholder={`e.g. ${placeholder}`}
            onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); void interpret(); } }} aria-label="Research request" />
        </label>
        <div className="request-actions">
          <div className="example-row"><span className="muted">Try:</span>{EXAMPLES.map((example) => <button type="button" key={example} className="example-chip" onClick={() => setText(example)}>{example.replace(/\.$/, "")}</button>)}</div>
          <ProviderChooser providers={providers} types={providerTypes} value={chosenProvider} onChange={chooseProvider} onOpenSettings={onOpenSettings} />
          <button className="button button-primary" type="submit" disabled={!text.trim() || busy === "interpret"}>{busy === "interpret" ? <><Spinner /> Interpreting…</> : <>Interpret request</>}</button>
        </div>
        {noProvider && <p className="footnote">No LLM provider is set up, so SUGAR uses its built-in interpreter. <button type="button" className="text-button" onClick={onOpenSettings}>Add a provider</button> for smarter interpretation and translation.</p>}
      </form>

      {interpretation?.needs_manual_entry && !plan && (
        <>
          {interpretation.clarifications.length > 0 && <div className="notice notice-info">{interpretation.clarifications.join(" ")}</div>}
          {interpretation.issues.filter((i) => i.field !== "topic").map((i) => <div className="notice notice-warn" key={i.message}>{i.message}</div>)}
          <ManualEntry initial={interpretation.request} platforms={platforms} onSubmit={(fields) => void submitManual(fields)} busy={busy === "manual"} />
        </>)}

      {projectId && <FeedsCard projectId={projectId} saved={overview?.settings?.rss_feeds || []} savedSites={overview?.settings?.web_seeds || []} onSaved={() => void onOverview()} onError={onError} />}

      {plan && <PlanPreview summary={summary} interpretation={interpretation} plan={plan} advanced={advanced} running={busy === "run"} canRun onRun={() => void runNow()}
        onEdit={() => setEditing("basic")} onAdvanced={() => setEditing("advanced")} onOpenSettings={onOpenSettings} />}

      {!plan && storedPlan && overview && (
        <section className="panel current-plan" aria-label="Current project plan">
          <div className="panel-heading"><div><span className="eyebrow">THIS PROJECT</span><h3>{overview.summary.research_question || storedPlan.topic}</h3></div>
            <div className="pill-row"><StatusPill status={overview.summary.status} />{lastRun && <span className="muted">Last run {relativeTime(lastRun.finished_at || lastRun.created_at)}</span>}</div></div>
          <dl className="summary-grid">{overview.plan_summary.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl>
          <div className="preview-actions">
            <button className="button button-primary" disabled={Boolean(busy)} onClick={() => void operate("rerun")}>Rerun</button>
            <button className="button button-secondary" onClick={() => setEditing("basic")}>Edit plan</button>
            {lastRun && <button className="button button-quiet" onClick={() => onOpenResults(lastRun.run_id)}>Open latest results</button>}
          </div>
          <Collapsible title="Refresh and rebuild options" hint="Five different operations — each does one thing" defaultOpen={advanced}>
            <ul className="operation-list">
              {OPERATIONS.map((op) => (
                <li key={op.id}><div><strong>{op.label}</strong><p>{op.detail}</p></div>
                  <button className="button button-secondary button-small" disabled={Boolean(busy) || !canOperate} onClick={() => void operate(op.id)}>{busy === op.id ? <Spinner /> : "Run"}</button></li>))}
            </ul>
          </Collapsible>
        </section>)}

      {proposal && proposal.interp.plan && (
        <section className="panel proposal" aria-label="Proposed plan">
          <div className="panel-heading"><div><span className="eyebrow">{proposal.kind === "reinterpret" ? "REINTERPRETED" : "REBUILT"} — NOT SAVED YET</span><h3>Review the proposed plan</h3></div></div>
          {proposal.interp.note && <p className="muted">{proposal.interp.note}</p>}
          <dl className="summary-grid">{proposal.interp.summary.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl>
          <p className="muted">{proposal.interp.plan.queries.filter((q) => q.enabled).length} searches planned{proposal.interp.warnings?.length ? ` · ${proposal.interp.warnings.join(" ")}` : ""}</p>
          <div className="preview-actions"><button className="button button-primary" disabled={busy === "accept"} onClick={() => void acceptProposal()}>Accept and save</button>
            <button className="button button-quiet" onClick={() => setProposal(null)}>Discard</button></div>
        </section>)}

      {!plan && !storedPlan && !interpretation && (
        <div className="how-it-works" aria-label="How it works">
          {[["1", "Describe", "Write what you want to research the way you would say it."], ["2", "Check", "SUGAR shows the plan it understood, and every assumption it made."], ["3", "Watch", "Follow searches, sources and translations as they happen."], ["4", "Inspect", "Every result keeps its source, query, and translation history."]].map(([n, title, detail]) => (
            <div key={n}><span className="how-n">{n}</span><strong>{title}</strong><p>{detail}</p></div>))}
        </div>)}

      {editing && (plan || storedPlan) && (
        <PlanEditor plan={(plan || storedPlan)!} platforms={platforms} providers={providers} advanced={editing === "advanced" || advanced} saving={busy === "save"}
          error={saveError} onSave={(edited) => void saveEdited(edited)} onCancel={() => { setEditing(""); setSaveError(""); }} />)}
    </section>
  );
}
