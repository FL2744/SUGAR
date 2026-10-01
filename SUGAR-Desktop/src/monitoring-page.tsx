import { useCallback, useEffect, useState, type FormEvent } from "react";
import { research } from "./research-api";
import type { Digest, Monitor } from "./research-types";
import { EmptyState, Pill, Spinner, relativeTime, titleCase } from "./ui";

const CADENCE_LABEL: Record<number, string> = { 1: "Every hour", 6: "Every 6 hours", 12: "Every 12 hours", 24: "Daily", 72: "Every 3 days", 168: "Weekly", 336: "Every 2 weeks", 720: "Monthly" };
const KIND_TONE: Record<string, "ok" | "warn" | "neutral" | "info"> = { new: "ok", reopened: "ok", closed: "warn", status: "warn", renamed: "info", moved: "info", activity: "info", removed: "neutral" };

function DigestCard({ digest, onOpenResults, onOpenRecord }: { digest: Digest; onOpenResults: (runId: string) => void; onOpenRecord: (entityId: string) => void }) {
  return (
    <li className="digest-card">
      <div className="digest-head"><strong>{digest.summary}</strong><small className="muted">{relativeTime(digest.at)} · {digest.trigger === "schedule" ? "scheduled" : "manual"}</small></div>
      {digest.institution_changes.length > 0 && <ul className="digest-changes">{digest.institution_changes.slice(0, 12).map((c, i) => (
        <li key={`${c.entity_id}${i}`}><Pill tone={KIND_TONE[c.kind] || "neutral"}>{titleCase(c.kind)}</Pill> <button className="text-button" onClick={() => onOpenRecord(c.entity_id)}>{c.name}</button> <small className="muted">{c.detail}</small></li>))}
        {digest.institution_changes.length > 12 && <li className="muted">and {digest.institution_changes.length - 12} more</li>}</ul>}
      {digest.new_items.length > 0 && <details><summary>{digest.counts.new_items} new item{digest.counts.new_items === 1 ? "" : "s"}</summary>
        <ul className="digest-items">{digest.new_items.map((i) => <li key={i.item_id}><a href={i.url} target="_blank" rel="noreferrer">{i.platform} ↗</a> <span dir="auto">{i.text}</span></li>)}</ul></details>}
      {digest.changed_items.length > 0 && <details><summary>{digest.counts.changed_items} changed item{digest.counts.changed_items === 1 ? "" : "s"}</summary>
        <ul className="digest-items">{digest.changed_items.map((i) => <li key={i.item_id}><a href={i.url} target="_blank" rel="noreferrer">{i.platform} ↗</a> <span dir="auto">{i.text}</span></li>)}</ul></details>}
      {digest.incomplete_sources.length > 0 && <div className="notice notice-warn">Could not read: {digest.incomplete_sources.join(", ")}.</div>}
      {digest.run_id && <button className="button button-quiet button-small" onClick={() => onOpenResults(digest.run_id)}>Open this pass's results</button>}
    </li>
  );
}

/** Keep the picture current: repeat the plan on a schedule and read what changed. */
export function MonitoringPage({ projectId, onOpenResults, onOpenRecord, onError }: { projectId: string; onOpenResults: (runId: string) => void; onOpenRecord: (entityId: string) => void; onError: (m: string) => void }) {
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [cadences, setCadences] = useState<number[]>([24, 168]);
  const [digests, setDigests] = useState<Digest[]>([]);
  const [busy, setBusy] = useState("");
  const [name, setName] = useState("");
  const [cadence, setCadence] = useState(168);
  const [note, setNote] = useState("");
  const load = useCallback(async () => {
    if (!projectId) return;
    try { const [m, d] = await Promise.all([research.monitors(projectId), research.digests(projectId)]); setMonitors(m.monitors); setCadences(m.cadences_hours); setDigests(d); }
    catch (e) { onError(e instanceof Error ? e.message : String(e)); }
  }, [projectId, onError]);
  useEffect(() => { void load(); const t = window.setInterval(() => void load(), 15000); return () => window.clearInterval(t); }, [load]);
  const guard = async (label: string, work: () => Promise<void>) => { setBusy(label); try { await work(); await load(); } catch (e) { onError(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); } };
  const create = (event: FormEvent) => { event.preventDefault(); void guard("save", async () => { await research.saveMonitor(projectId, { name, cadence_hours: cadence, note }); setName(""); setNote(""); }); };

  if (!projectId) return <section className="page-content"><EmptyState icon="◔" title="Open a project first">Monitoring repeats a project's research plan on a schedule.</EmptyState></section>;
  return (
    <section className="page-content monitoring-page">
      <div className="page-heading compact-heading">
        <div><div className="eyebrow">MONITORING <span className="eyebrow-line" /></div><h1>What changed since last time</h1>
          <p>A monitor repeats this project's current plan. Each pass ends with a digest of new items, changed items, and institutions that appeared, closed, were renamed or moved.</p></div>
        <div className="run-controls"><button className="button button-secondary" disabled={Boolean(busy)} onClick={() => void guard("checkpoint", async () => { await research.checkpointDigest(projectId); })}
          title="Compare the institution records with the last digest now">Check institutions now</button></div>
      </div>
      <p className="notice notice-info">Scheduled checks run while SUGAR is open on this computer or on the server it is connected to. A pass never starts while another run is active in the project.</p>

      <form className="panel monitor-form" onSubmit={create}>
        <div className="field-grid">
          <label className="field-block"><span>Name <em>Required</em></span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Weekly regional check" required /></label>
          <label className="field-block"><span>How often</span><select value={cadence} onChange={(e) => setCadence(Number(e.target.value))}>{cadences.map((h) => <option key={h} value={h}>{CADENCE_LABEL[h] || `Every ${h} hours`}</option>)}</select></label>
        </div>
        <label className="field-block"><span>Note</span><input value={note} onChange={(e) => setNote(e.target.value)} placeholder="What you are watching for (optional)" /></label>
        <div className="preview-actions"><button className="button button-primary" disabled={!name.trim() || busy === "save"}>{busy === "save" ? <Spinner /> : "Add monitor"}</button></div>
      </form>

      {monitors.length > 0 && <ul className="monitor-list">{monitors.map((m) => (
        <li key={m.id} className="panel">
          <div><strong>{m.name}</strong> <Pill tone={m.enabled ? "ok" : "neutral"}>{m.enabled ? CADENCE_LABEL[m.cadence_hours] || `Every ${m.cadence_hours}h` : "Paused"}</Pill>
            <small className="muted"> {m.last_run_at ? `last ran ${relativeTime(m.last_run_at)}${m.last_status ? ` · ${m.last_status}` : ""}` : "has not run yet"}{m.enabled && m.next_due_at ? ` · next ${relativeTime(m.next_due_at)}` : ""}</small>
            {m.note && <p className="muted">{m.note}</p>}</div>
          <div className="claim-actions">
            <button className="button button-secondary button-small" disabled={Boolean(busy)} onClick={() => void guard("run" + m.id, async () => { await research.runMonitor(projectId, m.id); })}>Run now</button>
            <button className="button button-quiet button-small" disabled={Boolean(busy)} onClick={() => void guard("toggle", async () => { await research.saveMonitor(projectId, { id: m.id, name: m.name, cadence_hours: m.cadence_hours, enabled: !m.enabled, note: m.note }); })}>{m.enabled ? "Pause" : "Resume"}</button>
            <button className="button button-quiet button-small" disabled={Boolean(busy)} onClick={() => { if (window.confirm(`Delete “${m.name}”? Past digests are kept.`)) void guard("del", async () => { await research.deleteMonitor(projectId, m.id); }); }}>Delete</button>
          </div></li>))}</ul>}

      <h2 className="section-heading">Digests</h2>
      {digests.length === 0 ? <EmptyState icon="◔" title="No digests yet">Add a monitor and run it, or use “Check institutions now” to record a baseline. Digests then show what changed from there.</EmptyState>
        : <ul className="digest-list">{digests.map((d) => <DigestCard key={d.id} digest={d} onOpenResults={onOpenResults} onOpenRecord={onOpenRecord} />)}</ul>}
    </section>
  );
}
