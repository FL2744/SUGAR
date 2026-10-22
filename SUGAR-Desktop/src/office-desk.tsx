import { useCallback, useEffect, useRef, useState } from "react";
import { downloadWorkspaceFile } from "./bridge";
import { research } from "./research-api";
import type { Digest, OfficeExport, OfficeOverview } from "./research-types";
import { Collapsible, Pill, Spinner, relativeTime, titleCase } from "./ui";

const message = (e: unknown) => e instanceof Error ? e.message : String(e);

export function LatestDigest({ projectId }: { projectId: string }) {
  const [digest, setDigest] = useState<Digest | null>(null);
  useEffect(() => { let active = true; setDigest(null); void research.digests(projectId).then((rows) => { if (active) setDigest(rows?.[0] || null); }).catch(() => undefined); return () => { active = false; }; }, [projectId]);
  return <div className="office-digest-banner"><strong>What changed</strong><span>{digest?.summary || "Record a baseline in the evidence desk, then monitor changes monthly."}</span><a href="#evidence-desk">Open evidence desk ↓</a></div>;
}

export function CountrySnapshotButton({ projectId, country, onError }: { projectId: string; country: string; onError: (message: string) => void }) {
  const [busy, setBusy] = useState(false);
  return <button className="button button-secondary button-small" disabled={!country || busy} title={country ? `Export a source-linked snapshot of ${country}` : "Choose a country first"} onClick={async () => {
    setBusy(true);
    try {
      const result = await research.countrySnapshot(projectId, country);
      await downloadWorkspaceFile(`sugar-file://${projectId}/${result.directory}/country-snapshot.html`, `${country}-snapshot.html`);
    } catch (e) { onError(message(e)); } finally { setBusy(false); }
  }}>{busy ? <><Spinner /> Building…</> : "Country snapshot (.html)"}</button>;
}

/** Office workflow stays outside the map canvas and uses the existing engine. */
export function OfficeDesk({ projectId, onChanged }: { projectId: string; onChanged: () => void }) {
  const [data, setData] = useState<OfficeOverview | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [country, setCountry] = useState("");
  const [rubric, setRubric] = useState("");
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState("en");
  const [edition, setEdition] = useState("US");
  const [channel, setChannel] = useState("");
  const [feeds, setFeeds] = useState<string[]>([]);
  const [feedNote, setFeedNote] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [bundle, setBundle] = useState<OfficeExport | null>(null);
  const generation = useRef(0);
  const refresh = useCallback(async () => {
    const current = ++generation.current;
    const [office, rules] = await Promise.all([research.office(projectId), research.officeRubric(projectId)]);
    if (current !== generation.current) return;
    if (!Array.isArray(office.countries) || !office.coding) throw new Error("The evidence desk needs the updated SUGAR engine. Restart the engine after updating.");
    setData(office); setRubric(JSON.stringify(rules, null, 2));
    setCountry((prior) => office.countries.includes(prior) ? prior : office.countries[0] || "");
  }, [projectId]);
  useEffect(() => {
    setData(null); setError(""); setNotice(""); setBundle(null); setFeeds([]); setSourceUrl("");
    if (projectId) void refresh().catch((e) => setError(message(e)));
    return () => { generation.current++; };
  }, [projectId, refresh]);
  const perform = async (key: string, work: () => Promise<void>) => {
    setBusy(key); setError(""); setNotice("");
    try { await work(); } catch (e) { setError(message(e)); } finally { setBusy(""); }
  };
  const capture = async (files: File[]) => {
    const pages = files.filter((f) => /\.html?$/i.test(f.name));
    if (!pages.length || pages.length > 20 || pages.reduce((n, f) => n + f.size, 0) > 25 * 1024 * 1024) {
      setError("Choose 1–20 HTML pages, totaling at most 25 MB."); return;
    }
    await perform("capture", async () => {
      const result = await research.capturePages(projectId, await Promise.all(pages.map(async (file) => ({ filename: file.name, source_url: pages.length === 1 ? sourceUrl.trim() : "", html: await file.text() }))));
      setNotice(`Imported ${result.imported} sanitized page(s). ${result.errors.map((e) => `${e.filename}: ${e.reason}`).join(" ")}`);
      onChanged(); await refresh();
    });
  };
  if (!projectId) return null;
  return <section id="evidence-desk" className="panel office-desk" aria-label="Evidence desk">
    <div className="panel-heading"><div><span className="eyebrow">EVIDENCE DESK · NO CREDENTIALS REQUIRED</span><h2>What changed, and what needs attention</h2></div>
      <button className="button button-secondary button-small" disabled={!!busy} onClick={() => void perform("assess", async () => {
        const result = await research.assessOffice(projectId); setData(result); setNotice(`Refreshed local evidence and proposed ${result.coded.proposed} new codes. No model calls.`); onChanged();
      })}>{busy === "assess" ? <><Spinner /> Assessing…</> : "Refresh local assessments"}</button></div>
    {error && <div className="notice notice-warn" role="alert">{error}</div>}
    {notice && <div className="notice notice-info" role="status">{notice}</div>}
    {data && <>
      <div className="office-digest"><strong>{data.latest_digest ? `Latest digest · ${relativeTime(data.latest_digest.at)}` : "No change baseline yet"}</strong>
        <p>{data.latest_digest?.summary || "Refresh local assessments to record a baseline. Scheduled monitoring can refresh and compare it every 30 days."}</p>
        {!!data.latest_digest?.institution_changes?.length && <ul>{data.latest_digest.institution_changes.slice(0, 5).map((c, i) => <li key={i}>{c.name}: {c.detail}</li>)}</ul>}
        <div className="pill-row"><Pill>{data.institutions} institutions</Pill><Pill tone={data.review_needed ? "warn" : "ok"}>{data.review_needed} need status review</Pill><Pill>{data.coding.items_coded} items coded</Pill></div></div>
      <div className="office-actions"><label className="field-block"><span>Country snapshot</span><select aria-label="Snapshot country" value={country} onChange={(e) => setCountry(e.target.value)}><option value="">Choose a country</option>{data.countries.map((c) => <option key={c}>{c}</option>)}</select></label>
        <CountrySnapshotButton projectId={projectId} country={country} onError={setError} />
        <button className="button button-secondary button-small" disabled={!!busy || !country} onClick={() => void perform("bundle", async () => { setBundle(await research.countrySnapshot(projectId, country)); })}>Country analysis bundle</button>
        <button className="button button-secondary button-small" disabled={!!busy} onClick={() => void perform("ai", async () => { setBundle(await research.approvedAIExport(projectId)); })}>Export for approved AI tool</button>
      </div>
      <small className="muted">Snapshots open in a browser without installation or network access. They include activity proposals, recent programs, narrative review candidates, coverage gaps and source links. AI packages contain evidence and a prompt for the tool your office approves; nothing is uploaded automatically.</small>
      {bundle && <div className="preview-actions"><button className="button button-primary button-small" onClick={() => void perform("download", () => downloadWorkspaceFile(`sugar-file://${projectId}/${bundle.archive}`, "sugar-evidence-package.zip"))}>Download package (.zip)</button><small>{bundle.files.length} files · full evidence, coding and provenance</small></div>}
    </>}
    <Collapsible title="Study rubric and multilingual terminology" hint="A–D priorities · six audiences · editable JSON file">
      <p className="footnote">Rules propose codes from source wording. Unmatched material remains uncoded. People confirm or reject proposals in item details. Edit aliases for renamed programs and alert_terms for narrative review candidates; keyword matches do not establish hostile intent. The agreed affiliation scale is separate from activity.</p>
      <textarea aria-label="Study rubric JSON" className="office-rubric" rows={12} value={rubric} onChange={(e) => setRubric(e.target.value)} spellCheck={false} />
      <div className="preview-actions"><button className="button button-secondary button-small" disabled={!!busy || !rubric} onClick={() => void perform("rubric", async () => {
        const saved = await research.saveOfficeRubric(projectId, JSON.parse(rubric)); setRubric(JSON.stringify(saved, null, 2)); setNotice("Saved study-rubric.json. Refresh local assessments to apply new rules; existing human decisions are retained.");
      })}>Save rubric</button><button className="button button-quiet button-small" disabled={!rubric} onClick={() => {
        const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([rubric], { type: "application/json" })); link.download = "study-rubric.json"; link.click(); URL.revokeObjectURL(link.href);
      }}>Download plain file</button>
        <label className="button button-quiet button-small file-button">Load file…<input type="file" accept=".json" className="sr-only" aria-label="Load study rubric file" onChange={(e) => { const f = e.target.files?.[0]; if (f) void f.text().then(setRubric).catch((e) => setError(message(e))); e.target.value = ""; }} /></label></div>
      {data && <div className="pill-row">{Object.entries(data.coding.proposed.priority_tier || {}).map(([tier, n]) => <Pill key={tier}>Tier {tier}: {n} coded items</Pill>)}{Object.entries(data.coding.proposed.audience_group || {}).map(([group, n]) => <Pill key={group}>{titleCase(group)}: {n}</Pill>)}</div>}
    </Collapsible>
    <Collapsible title="YouTube and local-language news feeds" hint="Build seeds from known accounts and regional news searches">
      <div className="office-fields"><label className="field-block"><span>Institution or news query</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Institution name or program" /></label>
        <label className="field-block"><span>Language</span><input aria-label="News language" value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="es" /></label><label className="field-block"><span>Country code</span><input aria-label="News country code" value={edition} onChange={(e) => setEdition(e.target.value.toUpperCase())} placeholder="MX" /></label></div>
      <label className="field-block"><span>YouTube channel ID or /channel/ URL (optional)</span><input value={channel} onChange={(e) => setChannel(e.target.value)} placeholder="UC…" /></label>
      <button className="button button-secondary button-small" disabled={!!busy} onClick={() => void perform("feeds", async () => { const result = await research.officeFeeds(projectId, { query, language, country: edition, channel }); setFeeds(result.feeds); setFeedNote([result.note, ...result.warnings].join(" ")); })}>Preview feed seeds</button>
      {feeds.length > 0 && <><ul className="office-feeds">{feeds.map((f) => <li key={f}><a href={f} target="_blank" rel="noreferrer">{f}</a></li>)}</ul><button className="button button-secondary button-small" disabled={!!busy} onClick={() => void perform("feeds-save", async () => {
        const current = await research.overview(projectId); const merged = [...new Set([...(current.settings.rss_feeds || []), ...feeds])];
        if (merged.length > 50) throw new Error("This would exceed 50 saved feeds. Remove unused feeds in Research first.");
        await research.saveSettings(projectId, { rss_feeds: merged }); setNotice("Feed seeds saved. Select RSS in the research plan to collect them."); onChanged();
      })}>Save these feeds</button></>}
      {feedNote && <p className="footnote">{feedNote}</p>}
    </Collapsible>
    <Collapsible title="Analyst capture inbox" hint="Drop saved HTML pages or scan the project drop folder">
      <p className="footnote">Save a page you are authorized to view. Drop up to 20 .html files below, choose a saved-page folder, or place them in research/capture-inbox in the project. Each needs its original canonical URL in the HTML, or a same-name .url.txt file in the drop folder. For one file, you can enter its URL below. Scripts, forms, hidden content and credential-like data are removed; only sanitized evidence is imported.</p>
      <label className="field-block"><span>Original URL (single-file imports)</span><input aria-label="Capture original URL" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://…" /></label>
      <div className="office-drop" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); if (!busy) void capture(Array.from(e.dataTransfer.files)); }}>
        <strong>Drop saved HTML pages here</strong><label className="button button-secondary button-small file-button">Choose pages…<input type="file" accept=".html,.htm" multiple disabled={!!busy} className="sr-only" aria-label="Saved HTML captures" onChange={(e) => { void capture(Array.from(e.target.files || [])); e.target.value = ""; }} /></label>
        <label className="button button-secondary button-small file-button">Choose folder…<input type="file" {...{ webkitdirectory: "" }} multiple disabled={!!busy} className="sr-only" aria-label="Saved page folder" onChange={(e) => { void capture(Array.from(e.target.files || [])); e.target.value = ""; }} /></label>
        <button className="button button-quiet button-small" disabled={!!busy} onClick={() => void perform("scan", async () => { const result = await research.scanCaptureInbox(projectId); setNotice(result.note || `Imported ${result.imported} pages. ${result.errors.map((e) => `${e.filename}: ${e.reason}`).join(" ")}`); onChanged(); await refresh(); })}>Scan project inbox</button>
      </div>
    </Collapsible>
  </section>;
}
