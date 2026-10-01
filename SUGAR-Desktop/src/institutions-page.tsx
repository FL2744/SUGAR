import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { research } from "./research-api";
import type { ClaimView, Confidence, Institution, InstitutionCandidate, InstitutionDetail, InstitutionList, RunSummary } from "./research-types";
import { NetworksPanel } from "./networks-panel";
import { EmptyState, Pill, Spinner, formatTime, relativeTime, titleCase } from "./ui";

const STATUSES = ["active", "closed", "renamed", "relocated", "unknown"] as const;
const TONE: Record<string, "ok" | "warn" | "neutral" | "error"> = { active: "ok", closed: "neutral", renamed: "warn", relocated: "warn", unknown: "neutral" };

export function ConfidencePill({ confidence }: { confidence: Confidence }) {
  return <Pill tone={confidence.level === "high" ? "ok" : confidence.level === "medium" ? "info" : "warn"} title={confidence.reasons.join(" · ")}>{titleCase(confidence.level)} confidence</Pill>;
}

const showValue = (value: unknown): string => Array.isArray(value) ? value.join(", ") : value === null || value === undefined ? "" : String(value);
const FIELD_LABELS: Record<string, string> = {
  name: "Name", network: "Network", status: "Status", status_date: "Status date", opened_date: "Opened", closed_date: "Closed", country: "Country", region: "Region", city: "City",
  address: "Address", latitude: "Latitude", longitude: "Longitude", location_precision: "Location precision", aliases: "Also known as", audiences: "Audiences",
  normalized_audiences: "Audiences (standard)", program_domains: "Programs", normalized_program_domains: "Programs (standard)", host_entities: "Host institutions",
  partner_entities: "Partners", public_links: "Links", accounts: "Accounts", description: "Description", delivery_modes: "Delivery",
};

function ClaimRow({ claim, canReview, onReview }: { claim: ClaimView; canReview: boolean; onReview: (state: string) => void }) {
  const tone = claim.review_state === "human_verified" ? "ok" : claim.review_state === "rejected" ? "error" : claim.review_state === "needs_followup" ? "warn" : "neutral";
  return (
    <li className="claim-row">
      <div className="claim-head">
        <strong>{showValue(claim.value)}</strong>
        <Pill tone={tone}>{claim.review_state === "human_verified" ? `Verified${claim.reviewer ? ` by ${claim.reviewer}` : ""}` : titleCase(claim.review_state)}</Pill>
        {claim.verified_at && <small className="muted">{formatTime(claim.verified_at, false)}</small>}
      </div>
      <ul className="claim-evidence">
        {claim.evidence.slice(0, 4).map((ref, index) => (
          <li key={index}>
            {ref.source_url ? <a href={String(ref.source_url)} target="_blank" rel="noreferrer">{new URL(String(ref.source_url)).host} ↗</a> : <span>Source</span>}
            {ref.quote ? <q dir="auto">{String(ref.quote)}</q> : ref.note ? <small className="muted">{String(ref.note)}</small> : null}
            {(ref.published_at || ref.retrieved_at) && <small className="muted"> {String(ref.published_at || ref.retrieved_at).slice(0, 10)}</small>}
          </li>))}
      </ul>
      {canReview && <div className="claim-actions">
        <button className="button button-secondary button-small" onClick={() => onReview("human_verified")} disabled={claim.review_state === "human_verified"}>✓ Verify</button>
        <button className="button button-quiet button-small" onClick={() => onReview("needs_followup")}>⚑ Follow up</button>
        <button className="button button-quiet button-small" onClick={() => onReview("rejected")}>✕ Reject</button>
      </div>}
    </li>
  );
}

function DetailDrawer({ projectId, entityId, author, others, onClose, onChanged, onError }: {
  projectId: string; entityId: string; author: string; others: Institution[]; onClose: () => void; onChanged: () => void; onError: (m: string) => void;
}) {
  const [detail, setDetail] = useState<InstitutionDetail | null>(null);
  const [mergeWith, setMergeWith] = useState("");
  const [source, setSource] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Awaited<ReturnType<typeof research.institutionHistory>> | null>(null);
  const [checking, setChecking] = useState(false);
  const load = useCallback(() => research.institution(projectId, entityId).then(setDetail).catch((e) => onError(e instanceof Error ? e.message : String(e))), [projectId, entityId, onError]);
  useEffect(() => { setDetail(null); void load(); }, [load]);
  const guard = async (work: () => Promise<InstitutionDetail>) => {
    setBusy(true);
    try { setDetail(await work()); onChanged(); } catch (e) { onError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  const order = ["status", "name", "network", "country", "region", "city", "address", "aliases", "normalized_program_domains", "program_domains", "normalized_audiences", "audiences", "host_entities", "partner_entities", "opened_date", "closed_date", "status_date", "description", "public_links", "accounts"];
  const shown = detail ? Object.keys(detail.fields).filter((f) => !["latitude", "longitude", "location_precision", "audience_descriptions", "program_descriptions", "normalized_delivery_modes", "delivery_mode_descriptions", "source_url"].includes(f))
    .sort((a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99)) : [];

  return (
    <div className="inspector-backdrop" onClick={onClose}>
      <aside className="evidence-inspector item-inspector institution-drawer" role="dialog" aria-modal="true" aria-label="Institution details" onClick={(event) => event.stopPropagation()}>
        <div className="inspector-top"><div><span className="eyebrow">INSTITUTION</span><button className="inspector-close" onClick={onClose} aria-label="Close details">×</button></div>
          {detail ? <div className="inspector-identity"><div><h2>{detail.name}</h2><span>{[detail.city, detail.country].filter(Boolean).join(", ") || "Location not recorded"}{detail.network ? ` · ${detail.network}` : ""}</span></div></div> : <div className="loading-block"><Spinner /> Loading…</div>}
          {detail && <div className="inspector-badges"><Pill tone={TONE[detail.status] || "neutral"}>{titleCase(detail.status)}</Pill><ConfidencePill confidence={detail.confidence} />
            {detail.last_verified ? <Pill tone="ok">Last verified {relativeTime(detail.last_verified)}</Pill> : <Pill tone="warn">Not verified yet</Pill>}
            {detail.conflicts.length > 0 && <Pill tone="warn">Sources disagree: {detail.conflicts.join(", ")}</Pill>}</div>}
        </div>
        <div className="inspector-content">
          {detail && <>
            <div className="inspector-section"><span className="eyebrow">WHY THIS RATING</span><ul className="reason-list">{detail.confidence.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              <small className="muted">The rating reflects how well the record is supported. It is not a measure of importance or influence.</small></div>
            {shown.map((field) => (
              <div className="inspector-section" key={field}><span className="eyebrow">{(FIELD_LABELS[field] || titleCase(field)).toUpperCase()}</span>
                <ul className="claim-list">{detail.fields[field].claims.map((claim) => (
                  <ClaimRow key={claim.claim_id} claim={claim} canReview onReview={(state) => void guard(() => research.reviewClaim(projectId, entityId, claim.claim_id, state, "", author))} />))}</ul></div>))}
            {detail.lifecycle.length > 0 && <div className="inspector-section"><span className="eyebrow">STATUS HISTORY</span>
              <ol className="transform-list">{detail.lifecycle.map((event, index) => <li key={index}><strong>{titleCase(String(event.status || event.event_type))}</strong>
                <small>{String(event.effective_date || event.observed_at || "").slice(0, 10)}{event.review_state === "human_verified" ? " · verified" : ""}</small></li>)}</ol></div>}
            <div className="inspector-section"><span className="eyebrow">LINKED ITEMS ({detail.links.length})</span>
              {detail.links.length === 0 ? <small className="muted">No collected items are linked yet.</small> : <ul className="claim-evidence">{detail.links.slice(0, 12).map((link) => (
                <li key={String(link.id)}><a href={String(link.url)} target="_blank" rel="noreferrer">{String(link.platform)} ↗</a>{link.quote ? <q dir="auto">{String(link.quote)}</q> : null}<small className="muted"> {String(link.published_at || link.retrieved_at || "").slice(0, 10)}</small></li>))}</ul>}</div>
            <div className="inspector-section"><span className="eyebrow">ADD A SOURCE</span>
              <div className="note-add"><input value={source} onChange={(e) => setSource(e.target.value)} placeholder="https://… (an official page, report, or article)" aria-label="Source address" />
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="What it shows (optional)" aria-label="What the source shows" />
                <button className="button button-secondary button-small" disabled={busy || !/^https?:\/\//i.test(source.trim())}
                  onClick={() => void guard(async () => { const next = await research.recordInstitution(projectId, { values: { name: detail.name }, entity_id: entityId, evidence: [{ url: source.trim(), note }], author }); setSource(""); setNote(""); return next; })}>Add</button></div></div>
            <div className="inspector-section"><span className="eyebrow">PAGE HISTORY (INTERNET ARCHIVE)</span>
              <button className="button button-secondary button-small" disabled={checking} onClick={async () => { setChecking(true); try { setHistory(await research.institutionHistory(projectId, entityId)); } catch (e) { onError(e instanceof Error ? e.message : String(e)); } finally { setChecking(false); } }}>{checking ? <><Spinner /> Checking…</> : "Check captured history of its pages"}</button>
              {history && <>{history.pages.length === 0 && history.errors.length === 0 && <small className="muted">No web pages are recorded for this institution yet. Add a source address above.</small>}
                {history.pages.map((page) => <div key={page.url} className="history-card"><a href={page.url} target="_blank" rel="noreferrer">{page.url}</a>
                  <small className="muted">{page.total} capture{page.total === 1 ? "" : "s"}{page.first_seen ? ` · first ${page.first_seen.slice(0, 10)}` : ""}{page.last_ok ? ` · last good ${page.last_ok.slice(0, 10)}` : ""}</small>
                  <ul>{page.signals.map((sig) => <li key={sig}>{sig}</li>)}</ul>
                  {page.snapshots.length > 0 && <a href={page.snapshots[page.snapshots.length - 1].archive_url} target="_blank" rel="noreferrer">Open the latest capture ↗</a>}</div>)}
                {history.errors.map((err) => <div key={err.url} className="notice notice-warn">{err.url}: {err.reason}</div>)}
                <small className="muted">{history.note}</small></>}</div>
            <div className="inspector-section"><span className="eyebrow">DUPLICATE?</span>
              <div className="note-add"><select value={mergeWith} onChange={(e) => setMergeWith(e.target.value)} aria-label="Merge a duplicate into this record"><option value="">Merge another record into this one…</option>
                {others.filter((o) => o.entity_id !== entityId).map((o) => <option key={o.entity_id} value={o.entity_id}>{o.name} {o.city ? `· ${o.city}` : ""}</option>)}</select>
                <button className="button button-secondary button-small" disabled={busy || !mergeWith} onClick={() => { if (window.confirm("Merge that record into this one? Its sources and claims move here; the duplicate stays in the history.")) void guard(() => research.mergeInstitutions(projectId, entityId, mergeWith, "", author)); }}>Merge</button></div></div>
          </>}
        </div>
      </aside>
    </div>
  );
}

function CandidatesPanel({ projectId, runs, author, onClose, onRecorded, onError }: {
  projectId: string; runs: RunSummary[]; author: string; onClose: () => void; onRecorded: () => void; onError: (m: string) => void;
}) {
  const [runId, setRunId] = useState(runs[0]?.run_id || "");
  const [mode, setMode] = useState<"auto" | "deterministic">("auto");
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState<{ candidates: InstitutionCandidate[]; warnings: string[]; scanned: number; model_used: boolean } | null>(null);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const scan = async () => {
    setBusy("scan"); setResult(null);
    try { setResult(await research.institutionCandidates(projectId, runId, mode)); } catch (e) { onError(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); }
  };
  const record = async (candidate: InstitutionCandidate) => {
    setBusy(candidate.name);
    try {
      await research.recordInstitution(projectId, {
        values: { name: candidate.name, country: candidate.country, city: candidate.city || "", status: candidate.status_hint || undefined },
        evidence: candidate.evidence.map((e) => ({ run_id: runId, item_id: e.item_id, quote: e.quote })), author,
      });
      setDone((d) => ({ ...d, [candidate.name]: true })); onRecorded();
    } catch (e) { onError(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); }
  };
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="modal candidates-panel" role="dialog" aria-modal="true" aria-labelledby="cand-title" onClick={(event) => event.stopPropagation()}>
        <header className="modal-head"><div><span className="eyebrow">FIND INSTITUTIONS</span><h2 id="cand-title">Names mentioned in a run</h2></div><button className="text-button" onClick={onClose}>Close</button></header>
        <div className="modal-body">
          <p>SUGAR looks for institution names and quotes the sentence each came from. Nothing is recorded until you choose it, and every record keeps its source.</p>
          <div className="toolbar">
            <select value={runId} onChange={(e) => setRunId(e.target.value)} aria-label="Run to scan">{runs.map((r) => <option key={r.run_id} value={r.run_id}>{titleCase(r.kind)} · {relativeTime(r.finished_at || r.created_at)} · {r.counts?.collected ?? 0} items</option>)}</select>
            <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} aria-label="How to scan"><option value="auto">Patterns + your AI model</option><option value="deterministic">Patterns only (no AI)</option></select>
            <button className="button button-primary" onClick={() => void scan()} disabled={!runId || busy === "scan"}>{busy === "scan" ? <><Spinner /> Scanning…</> : "Scan"}</button>
          </div>
          {result && <p className="muted" role="status">Scanned {result.scanned} items{result.model_used ? " with your AI model" : ""}; found {result.candidates.length}.</p>}
          {result?.warnings.map((w) => <div key={w} className="notice notice-warn">{w}</div>)}
          <ul className="candidate-list">
            {result?.candidates.map((c) => (
              <li key={c.name}>
                <div><strong dir="auto">{c.name}</strong> <small className="muted">{c.mentions} mention{c.mentions === 1 ? "" : "s"}{c.country ? ` · ${c.country}` : ""} · {c.method}</small>
                  {c.status_hint && <Pill tone={TONE[c.status_hint] || "neutral"} title="A cue in the text, not a finding">Text suggests: {c.status_hint}</Pill>}
                  <q dir="auto">{c.evidence[0]?.quote}</q></div>
                {c.already_recorded ? <Pill>Recorded</Pill> : done[c.name] ? <Pill tone="ok">Recorded ✓</Pill>
                  : <button className="button button-secondary button-small" disabled={Boolean(busy)} onClick={() => void record(c)}>{busy === c.name ? <Spinner /> : "Record"}</button>}
              </li>))}
          </ul>
        </div>
      </section>
    </div>
  );
}

export function InstitutionsPage({ projectId, runs, author, onError, onOpenMap, openId = "", onOpened }: { projectId: string; runs: RunSummary[]; author: string; onError: (m: string) => void; onOpenMap: () => void; openId?: string; onOpened?: () => void }) {
  const [data, setData] = useState<InstitutionList | null>(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [network, setNetwork] = useState("");
  const [status, setStatus] = useState("");
  const [level, setLevel] = useState("");
  const [open, setOpen] = useState("");
  const [finder, setFinder] = useState(false);
  const [adding, setAdding] = useState(false);
  const [networksOpen, setNetworksOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => { if (openId) { setOpen(openId); onOpened?.(); } }, [openId, onOpened]);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try { setData(await research.institutions(projectId, { q, network, status, confidence: level })); }
    catch (e) { onError(e instanceof Error ? e.message : String(e)); } finally { setLoading(false); }
  }, [projectId, q, network, status, level, onError]);
  useEffect(() => { const t = window.setTimeout(() => void load(), q ? 250 : 0); return () => window.clearTimeout(t); }, [load, q]);

  const geocode = async () => {
    setBusy("geo"); setMsg("");
    try {
      const r = await research.geocodeInstitutions(projectId);
      setMsg(`Placed ${r.placed.length} institution${r.placed.length === 1 ? "" : "s"} on the map${r.failed.length ? `; ${r.failed.length} could not be placed (${r.failed[0].reason})` : ""}.`);
      await load();
    } catch (e) { onError(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); }
  };
  const networks = useMemo(() => data?.facets.networks || [], [data]);

  if (!projectId) return <section className="page-content"><EmptyState icon="⌂" title="Open a project first">Institutions are recorded inside a research project.</EmptyState></section>;

  return (
    <section className="page-content institutions-page-new">
      <div className="page-heading compact-heading">
        <div><div className="eyebrow">INSTITUTIONS <span className="eyebrow-line" /></div><h1>Institutions and what supports them</h1>
          <p>Each record is built from sources you can open. A person verifies the claims that matter, and the record shows when.</p></div>
        <div className="run-controls">
          <button className="button button-secondary" onClick={() => setFinder(true)} disabled={runs.length === 0} title={runs.length ? "" : "Run a search first"}>Find in a run</button>
          <button className="button button-secondary" onClick={() => setAdding(true)}>Add institution</button>
          <button className="button button-secondary" onClick={() => setNetworksOpen(true)}>Networks &amp; imports</button>
          <button className="button button-primary" onClick={onOpenMap}>View on map</button>
        </div>
      </div>

      <div className="toolbar results-toolbar">
        <div className="search-field"><span aria-hidden="true">⌕</span><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, place, program" aria-label="Search institutions" /></div>
        <select value={network} onChange={(e) => setNetwork(e.target.value)} aria-label="Network"><option value="">All networks</option>{networks.map((f) => <option key={f.key} value={f.key === "unassigned" ? "" : f.key}>{f.key} ({f.count})</option>)}</select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">Any status</option>{STATUSES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</select>
        <select value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Confidence"><option value="">Any confidence</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>
        {data && data.unplaced > 0 && <button className="button button-quiet" onClick={() => void geocode()} disabled={busy === "geo"}>{busy === "geo" ? <><Spinner /> Placing…</> : `Place ${data.unplaced} on the map`}</button>}
      </div>
      {msg && <div className="notice notice-info" role="status">{msg}</div>}

      {loading && !data && <div className="loading-block"><Spinner /> Loading institutions…</div>}
      {data && data.total === 0 && <EmptyState icon="⌂" title="No institutions yet" action={<button className="button button-primary" onClick={() => setFinder(true)} disabled={runs.length === 0}>Find institutions in a run</button>}>
        Run a search, then use “Find in a run” to turn the names in your results into source-backed records. You can also add one directly with a source link.</EmptyState>}
      {data && data.total > 0 && (
        <div className="project-table" role="table" aria-label="Institutions">
          <div className="project-table-head" role="row"><span role="columnheader">Institution</span><span role="columnheader">Status</span><span role="columnheader">Where</span><span role="columnheader">Support</span><span role="columnheader">Last verified</span></div>
          {data.institutions.map((row) => (
            <button key={row.entity_id} className="project-row" role="row" onClick={() => setOpen(row.entity_id)}>
              <span role="cell"><strong dir="auto">{row.name}</strong>{row.network && <small className="muted"> {row.network}</small>}</span>
              <span role="cell"><Pill tone={TONE[row.status] || "neutral"}>{titleCase(row.status)}</Pill></span>
              <span role="cell">{[row.city, row.country].filter(Boolean).join(", ") || <span className="muted">not recorded</span>}{!row.placed && (row.city || row.country) ? <small className="muted"> · not on map</small> : null}</span>
              <span role="cell"><ConfidencePill confidence={row.confidence} /> <small className="muted">{row.source_count} source{row.source_count === 1 ? "" : "s"}</small></span>
              <span role="cell">{row.last_verified ? relativeTime(row.last_verified) : <span className="muted">never</span>}</span>
            </button>))}
        </div>)}

      {open && <DetailDrawer projectId={projectId} entityId={open} author={author} others={data?.institutions || []} onClose={() => setOpen("")} onChanged={() => void load()} onError={onError} />}
      {finder && <CandidatesPanel projectId={projectId} runs={runs} author={author} onClose={() => setFinder(false)} onRecorded={() => void load()} onError={onError} />}
      {networksOpen && <NetworksPanel projectId={projectId} onClose={() => setNetworksOpen(false)} onChanged={() => void load()} onError={onError} />}
      {adding && <AddInstitution projectId={projectId} author={author} onClose={() => setAdding(false)} onSaved={(id) => { setAdding(false); void load(); setOpen(id); }} onError={onError} />}
    </section>
  );
}

function AddInstitution({ projectId, author, onClose, onSaved, onError }: { projectId: string; author: string; onClose: () => void; onSaved: (id: string) => void; onError: (m: string) => void }) {
  const [form, setForm] = useState({ name: "", network: "", country: "", city: "", status: "unknown", url: "", note: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const saved = await research.recordInstitution(projectId, { values: { name: form.name.trim(), network: form.network.trim(), country: form.country.trim(), city: form.city.trim(), status: form.status === "unknown" ? undefined : form.status },
        evidence: [{ url: form.url.trim(), note: form.note }], author });
      onSaved(saved.entity_id);
    } catch (e) { onError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" role="dialog" aria-modal="true" aria-labelledby="add-inst" onClick={(event) => event.stopPropagation()} onSubmit={(event) => void submit(event)}>
        <header className="modal-head"><div><span className="eyebrow">NEW RECORD</span><h2 id="add-inst">Add an institution</h2></div><button type="button" className="text-button" onClick={onClose}>Close</button></header>
        <div className="modal-body form-stack">
          <label className="field-block"><span>Name <em>Required</em></span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required autoFocus /></label>
          <div className="field-grid">
            <label className="field-block"><span>Network</span><input value={form.network} onChange={(e) => setForm({ ...form, network: e.target.value })} placeholder="e.g. the network it belongs to" /></label>
            <label className="field-block"><span>Status</span><select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>{STATUSES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</select></label>
            <label className="field-block"><span>City</span><input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /></label>
            <label className="field-block"><span>Country</span><input value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} /></label>
          </div>
          <label className="field-block"><span>Source address <em>Required</em></span><input type="url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://…" required /></label>
          <label className="field-block"><span>What the source shows</span><input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
          <p className="footnote">Every record needs a source you can open. You can verify its claims afterward.</p>
        </div>
        <footer className="modal-foot"><button type="button" className="button button-quiet" onClick={onClose}>Cancel</button><button className="button button-primary" disabled={busy || !form.name.trim() || !/^https?:\/\//i.test(form.url.trim())}>{busy ? <Spinner /> : "Save"}</button></footer>
      </form>
    </div>
  );
}
