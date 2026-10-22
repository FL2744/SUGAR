import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { downloadWorkspaceFile } from "./bridge";
import { research } from "./research-api";
import type { Institution, InstitutionList, NetworkRow, OverlapResult, PostMap } from "./research-types";
import { NetworkMap, type Basemap, type Line, type MapMode, type PostLayers } from "./network-map";
import { ConfidencePill } from "./institutions-page";
import { axisSummary, timelineBins, windowPosts, type PostStyle } from "./map-data";
import { PostTimeline } from "./post-timeline";
import { Collapsible, EmptyState, Pill, Spinner, formatTime, relativeTime, titleCase } from "./ui";

const WINDOWS: Array<[string, string]> = [["", "All time"], ["2024-01-01", "Since 2024"], ["12m", "Last 12 months"], ["6m", "Last 6 months"]];
const sinceDate = (value: string): string => {
  if (!value || /^\d{4}-/.test(value)) return value;
  const months = Number(value.replace("m", ""));
  const d = new Date(); d.setMonth(d.getMonth() - months);
  return d.toISOString().slice(0, 10);
};

/** Where institutions are, what they are doing, and where networks sit near each other. Every marker opens to its sources. */
export function MapPage({ projectId, dark, onOpenRecord, onOpenInstitutions }: { projectId: string; dark: boolean; onOpenRecord: (entityId: string) => void; onOpenInstitutions: () => void }) {
  const [data, setData] = useState<InstitutionList | null>(null);
  const [networks, setNetworks] = useState<NetworkRow[]>([]);
  const [hidden, setHidden] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState("");
  const [level, setLevel] = useState("");
  const [country, setCountry] = useState("");
  const [program, setProgram] = useState("");
  const [audience, setAudience] = useState("");
  const [windowKey, setWindowKey] = useState("");
  const [mode, setMode] = useState<MapMode>("points");
  const [showLines, setShowLines] = useState(false);
  const [nearKm, setNearKm] = useState(25);
  const [overlap, setOverlap] = useState<OverlapResult | null>(null);
  const [view, setView] = useState<"map" | "list">("map");
  const [selected, setSelected] = useState("");
  const [allPosts, setPosts] = useState<PostMap | null>(null);
  const [basemap, setBasemap] = useState<Basemap>(dark ? "dark" : "streets");
  const [layers, setLayers] = useState<PostLayers>({ posts: true, targets: true, flows: false, institutions: true });
  const [selectedPost, setSelectedPost] = useState("");
  const [verdictFilter, setVerdictFilter] = useState("");
  const [days, setDays] = useState("");
  const [selectedTarget, setSelectedTarget] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [sort, setSort] = useState<"newest" | "oldest">("newest");
  const [postStyle, setPostStyle] = useState<PostStyle>("points");
  const [sentiment, setSentiment] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [frame, setFrame] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const [listPage, setListPage] = useState(0);
  const requestSeq = useRef(0);
  const bins = useMemo(() => timelineBins(allPosts?.pins || []), [allPosts]);
  const timeDomain = useMemo<[number, number] | undefined>(() => bins.length ? [Date.parse(`${bins[0].start}T00:00:00Z`), Date.parse(`${bins[bins.length - 1].end}T23:59:59Z`)] : undefined, [bins]);
  const effectiveUntil = frame !== null ? bins[frame]?.end || until : until;
  const posts = useMemo(() => windowPosts(allPosts, since, effectiveUntil, sort), [allPosts, since, effectiveUntil, sort]);
  const rangeError = Boolean(since && effectiveUntil && since > effectiveUntil);
  useEffect(() => { setPlaying(false); setFrame(null); }, [allPosts]);
  useEffect(() => { setListPage(0); }, [since, effectiveUntil, sort, verdictFilter, days]);
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => setFrame((current) => Math.min((current ?? -1) + 1, bins.length - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [playing, bins.length]);
  useEffect(() => { if (frame !== null && frame >= bins.length - 1) setPlaying(false); }, [frame, bins.length]);
  const changeDates = (start: string, end: string) => { setPlaying(false); setFrame(null); setSince(start); setUntil(end); };

  const load = useCallback(async () => {
    if (!projectId) return;
    const seq = ++requestSeq.current;
    setLoading(true); setError("");
    try {
      const [list, nets, pm] = await Promise.all([research.institutions(projectId, { status, confidence: level, country, program, audience, since: sinceDate(windowKey) }), research.networks(projectId),
        research.postMap(projectId, { verdict: verdictFilter, days }).catch((e) => { if (seq === requestSeq.current) setError(`Posts could not be loaded: ${e instanceof Error ? e.message : String(e)}`); return null; })]);
      if (seq === requestSeq.current) { setData(list); setNetworks(nets); setPosts(pm); }
    } catch (e) { if (seq === requestSeq.current) setError(e instanceof Error ? e.message : String(e)); } finally { if (seq === requestSeq.current) setLoading(false); }
  }, [projectId, status, level, country, program, audience, windowKey, verdictFilter, days]);
  useEffect(() => { void load(); }, [load]);

  const subjects = useMemo(() => networks.filter((n) => n.role === "subject").map((n) => n.name), [networks]);
  const references = useMemo(() => networks.filter((n) => n.role === "reference").map((n) => n.name), [networks]);
  useEffect(() => {
    if (!projectId || !subjects.length || !references.length) { setOverlap(null); return; }
    void research.overlap(projectId, { subject: subjects.join(","), reference: references.join(","), bands: `5,${nearKm},100,250`, country }).then(setOverlap).catch(() => setOverlap(null));
  }, [projectId, subjects, references, nearKm, country, data]);

  const visible = useMemo(() => (data?.institutions || []).filter((r) => !hidden[r.network || ""]), [data, hidden]);
  const byId = useMemo(() => Object.fromEntries((data?.institutions || []).map((r) => [r.entity_id, r])), [data]);
  const lines: Line[] = useMemo(() => {
    if (!showLines || !overlap) return [];
    return overlap.rows.flatMap((row) => {
      const from = byId[row.entity_id], to = row.nearest_reference ? byId[row.nearest_reference.entity_id] : undefined;
      if (!from?.placed || !to?.placed || row.nearest_reference!.distance_km > nearKm || hidden[from.network || ""] || hidden[to.network || ""]) return [];
      return [{ from: [from.longitude as number, from.latitude as number], to: [to.longitude as number, to.latitude as number] } as Line];
    });
  }, [showLines, overlap, byId, nearKm, hidden]);

  const pickedTarget = posts?.targets.find((t) => t.name === selectedTarget);
  const targetPosts = useMemo(() => { const ids = new Set(pickedTarget?.item_ids || []); return (posts?.pins || []).filter((p) => ids.has(p.item_id)); }, [pickedTarget, posts]);
  const exportMapped = async (target = "") => {
    setExporting(true); setError("");
    try {
      const result = await research.exportMap(projectId, { since, until: effectiveUntil, verdict: verdictFilter, days, target });
      await downloadWorkspaceFile(`sugar-file://${projectId}/${result.archive}`, target ? `posts-about-${target.replace(/\W+/g, "-")}.zip` : "mapped-posts-analysis.zip");
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setExporting(false); }
  };
  const pickedPost = posts?.pins.find((p) => p.item_id === selectedPost);
  const setVerified = async (itemId: string, verified: boolean) => {
    try {
      const done = await research.postReview(projectId, itemId, { kind: "verdict", verdict: verified ? "relevant" : "" });
      setPosts((cur) => cur && { ...cur, pins: cur.pins.map((p) => p.item_id === itemId ? { ...p, verified, verdict: done.review.verdict, verified_by: verified ? done.review.verdict_by : "", verified_at: verified ? done.review.verdict_at : "" } : p) });
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };

  if (!projectId) return <section className="page-content"><EmptyState icon="⌖" title="Open a project first">The map shows the institutions recorded in a project.</EmptyState></section>;
  const picked: Institution | undefined = byId[selected];
  const pickedOverlap = overlap?.rows.find((r) => r.entity_id === selected);
  const near = overlap ? overlap.by_country.reduce((n, c) => n + c.subjects_near_reference, 0) : 0;

  return (
    <section className="page-content map-page">
      <div className="page-heading compact-heading">
        <div><div className="eyebrow">MAP <span className="eyebrow-line" /></div><h1>Where institutions are, and where networks meet</h1>
          <p>Distances are computed from recorded coordinates, not findings of influence.</p></div>
        <div className="run-controls">
          <div className="segmented" role="radiogroup" aria-label="View">{(["map", "list"] as const).map((v) => <button key={v} role="radio" aria-checked={view === v} className={view === v ? "on" : ""} onClick={() => setView(v)}>{titleCase(v)}</button>)}</div>
          <button className="button button-secondary" onClick={onOpenInstitutions}>Institutions</button>
          <button className="button button-secondary" onClick={() => void exportMapped()} disabled={exporting || rangeError || !posts?.pins.length}>{exporting ? <Spinner /> : "Export mapped posts"}</button>
        </div>
      </div>
      {error && <div className="notice notice-warn" role="alert">{error}</div>}
      {rangeError && <div className="notice notice-warn" role="alert">The start date must be on or before the through date.</div>}

      <div className="map-layout">
        <div className="map-main">
          <div className="map-toolbar" role="toolbar" aria-label="Map layers">
            <div className="chip-group" role="group" aria-label="Layers">
              <button className="chip-toggle" aria-pressed={layers.posts} onClick={() => setLayers({ ...layers, posts: !layers.posts })}><span className="swatch post" aria-hidden="true" /> Posts <small>{posts?.pins.length ?? 0}</small></button>
              <button className="chip-toggle" aria-pressed={layers.targets} onClick={() => setLayers({ ...layers, targets: !layers.targets })}><span className="swatch target" aria-hidden="true" /> Targets <small>{posts?.targets.length ?? 0}</small></button>
              <button className="chip-toggle" aria-pressed={layers.flows} onClick={() => setLayers({ ...layers, flows: !layers.flows })}>Origin → target</button>
              <button className="chip-toggle" aria-pressed={layers.institutions} onClick={() => setLayers({ ...layers, institutions: !layers.institutions })}>Institutions</button>
              {networks.map((n) => <button key={n.name || "none"} className="chip-toggle chip-sub" aria-pressed={!hidden[n.name]} title={`Show or hide ${n.label}`} onClick={() => setHidden({ ...hidden, [n.name]: !hidden[n.name] })}><span className={`swatch ${n.role}`} aria-hidden="true" /> {n.label} <small>{n.institutions}</small></button>)}
            </div>
            <div className="map-toolbar-end">
              <div className="segmented" role="radiogroup" aria-label="Basemap">{(["dark", "streets", "terrain"] as const).map((v) => <button key={v} role="radio" aria-checked={basemap === v} className={basemap === v ? "on" : ""} onClick={() => setBasemap(v)}>{titleCase(v)}</button>)}</div>
            </div>
          </div>
          <Collapsible title="Filters and options" hint="Time, verification, status, place, program, audience, style"
            badge={[days, verdictFilter, windowKey, status, level, country, program, audience].filter(Boolean).length ? <Pill tone="info">{[days, verdictFilter, windowKey, status, level, country, program, audience].filter(Boolean).length} on</Pill> : undefined}>
            <div className="filter-grid">
              <label className="field-block"><span>Posts shown</span><select value={verdictFilter} onChange={(e) => setVerdictFilter(e.target.value)}><option value="">All posts</option><option value="relevant">Verified only</option><option value="none">Not yet checked</option></select></label>
              <label className="field-block"><span>Posted in</span><select value={days} onChange={(e) => setDays(e.target.value)}><option value="">Any time</option><option value="1">Last 24 hours</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select></label>
              <label className="check-row"><input type="checkbox" checked={sentiment} onChange={(e) => { setSentiment(e.target.checked); if (!e.target.checked && ["valence", "intensity", "direction"].includes(postStyle)) setPostStyle("points"); }} /><span>Enable exploratory language axes</span></label>
              <label className="field-block"><span>Institution evidence from</span><select value={windowKey} onChange={(e) => setWindowKey(e.target.value)}>{WINDOWS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
              <label className="field-block"><span>Status</span><select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Any</option>{["active", "closed", "renamed", "relocated", "unknown"].map((x) => <option key={x} value={x}>{titleCase(x)}</option>)}</select></label>
              <label className="field-block"><span>Confidence</span><select value={level} onChange={(e) => setLevel(e.target.value)}><option value="">Any</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
              <label className="field-block"><span>Country</span><select value={country} onChange={(e) => setCountry(e.target.value)}><option value="">All</option>{data?.facets.countries.map((f) => <option key={f.key} value={f.key === "unknown" ? "" : f.key}>{f.key} ({f.count})</option>)}</select></label>
              <label className="field-block"><span>Program</span><select value={program} onChange={(e) => setProgram(e.target.value)}><option value="">Any</option>{data?.facets.programs.map((f) => <option key={f.key} value={f.key}>{titleCase(f.key)} ({f.count})</option>)}</select></label>
              <label className="field-block"><span>Audience</span><select value={audience} onChange={(e) => setAudience(e.target.value)}><option value="">Any</option>{data?.facets.audiences.map((f) => <option key={f.key} value={f.key}>{titleCase(f.key)} ({f.count})</option>)}</select></label>
              <div className="field-block"><span>Institution style</span>
                <div className="segmented" role="radiogroup" aria-label="Map style">{([["points", "Points"], ["heat", "Activity heat"]] as const).map(([v, l]) => <button key={v} role="radio" aria-checked={mode === v} className={mode === v ? "on" : ""} onClick={() => setMode(v)}>{l}</button>)}</div>
                <small className="muted">Heat reflects recent linked items and recorded programs, not influence.</small></div>
              {references.length > 0 && subjects.length > 0 && <div className="field-block"><label className="check-row"><input type="checkbox" checked={showLines} onChange={(e) => setShowLines(e.target.checked)} /><span>Link each subject to its nearest reference within</span></label>
                <select value={nearKm} onChange={(e) => setNearKm(Number(e.target.value))} aria-label="Distance"><option value={5}>5 km</option><option value={25}>25 km</option><option value={100}>100 km</option><option value={250}>250 km</option></select></div>}
            </div>
          </Collapsible>
          <div className="map-visual-controls">
            <label>Color posts by <select aria-label="Post map coloring" value={postStyle} onChange={(e) => setPostStyle(e.target.value as PostStyle)}>
              <option value="points">Location and review</option><option value="density">Origin density</option><option value="recency">Publication time</option>
              {sentiment && <><option value="valence">Positive / negative language</option><option value="intensity">Language intensity</option><option value="direction">Inward / outward language</option></>}
            </select></label>
            <label>Sort posts <select aria-label="Map post publication order" value={sort} onChange={(e) => setSort(e.target.value as "newest" | "oldest")}><option value="newest">Newest first</option><option value="oldest">Oldest first</option></select></label>
          </div>
          <Collapsible title="Posts over time" hint={since || effectiveUntil ? `${since || "First dated post"} → ${effectiveUntil || "Latest post"}` : "Date range, publication counts and time playback"}>
            <PostTimeline bins={bins} since={since} until={effectiveUntil} frame={frame} playing={playing} onDates={changeDates}
              onFrame={(n) => { setPlaying(false); setFrame(n); if (since && since > bins[n].end) setSince(""); }}
              onPlay={() => { if (playing) { setPlaying(false); return; } const first = Math.max(0, bins.findIndex((b) => !since || b.end >= since)); if (frame === null || frame >= bins.length - 1) setFrame(first); setPlaying(true); }}
              onReset={() => changeDates("", "")} />
            <p className="footnote">Counts cover mapped posts. Posts with unknown publication dates appear in All time and are excluded from dated views.</p>
          </Collapsible>
          {sentiment && <div className="map-axis-summary" role="status">{(["valence", "intensity", "direction"] as const).map((axis) => { const score = axisSummary(posts?.pins || [], axis); return <span key={axis}>{titleCase(axis)}: <strong>{score.mean === null ? "Unscored" : score.mean.toFixed(2)}</strong> <small>(n={score.n.toLocaleString()})</small></span>; })}<small>{allPosts?.sentiment_note || "Exploratory English lexical indicators, including English translations. Unsupported language is unscored."}</small></div>}
          {(posts?.targets.length ?? 0) > 0 && <div className="top-strip" role="group" aria-label="Top targets"><span className="muted">Where posts are about:</span>
            {posts!.targets.slice(0, 8).map((t) => <button key={t.name} className={`chip-toggle ${selectedTarget === t.name ? "on" : ""}`} aria-pressed={selectedTarget === t.name} onClick={() => { setSelected(""); setSelectedPost(""); setSelectedTarget(t.name); }}>{t.name} <strong>{t.posts}</strong>{t.last_24h > 0 && <small> · {t.last_24h} today</small>}</button>)}</div>}

          <div className="map-stats" role="status">
            {loading && <Spinner />}<strong>{visible.filter((r) => r.placed).length}</strong> institutions placed · <strong>{data?.unplaced ?? 0}</strong> not placed · <strong>{(posts?.pins.length ?? 0).toLocaleString()}</strong> of {(allPosts?.pins.length ?? 0).toLocaleString()} located posts
            {allPosts?.coverage && <> · {allPosts.coverage.unlocated_posts.toLocaleString()} posts without a mapped location</>}
            {overlap && <> · <strong>{near}</strong> subject institutions have a reference institution within {nearKm} km</>}
          </div>
          {view === "map" ? <NetworkMap key={projectId} rows={visible} networks={networks} mode={mode} lines={lines} selectedId={selected} onSelect={(id) => { setSelectedPost(""); setSelectedTarget(""); setSelected(id); }} basemap={basemap} postStyle={postStyle} timeDomain={timeDomain}
            posts={posts} layers={layers} selectedPost={selectedPost} onSelectPost={(id) => { setSelected(""); setSelectedTarget(""); setSelectedPost(id); }}
            selectedTarget={selectedTarget} onSelectTarget={(name) => { setSelected(""); setSelectedPost(""); setSelectedTarget(name); }} />
            : <div className="project-table" role="table" aria-label="Institutions on the map">
                <div className="project-table-head" role="row"><span role="columnheader">Institution</span><span role="columnheader">Status</span><span role="columnheader">Where</span><span role="columnheader">Support</span></div>
                {layers.posts && (posts?.pins || []).slice(listPage * 100, (listPage + 1) * 100).map((p) => <button key={p.item_id} className="project-row" role="row" onClick={() => { setSelected(""); setSelectedPost(p.item_id); }}><span role="cell"><strong dir="auto">{p.author || "Unknown author"}</strong> <small className="muted">{p.platform} · {p.published_at ? p.published_at.slice(0, 10) : "date unknown"}</small></span>
                  <span role="cell">{p.verified ? "Verified" : "Not verified"}</span><span role="cell">{p.origin ? p.origin.label : p.inferred_location ? `About ${p.inferred_location.name}` : "—"}</span><span role="cell"><small dir="auto">{p.original_text.slice(0, 80)}</small></span></button>)}
                {visible.map((r) => <button key={r.entity_id} className="project-row" role="row" onClick={() => setSelected(r.entity_id)}><span role="cell"><strong dir="auto">{r.name}</strong> <small className="muted">{r.network}</small></span>
                  <span role="cell">{titleCase(r.status)}</span><span role="cell">{[r.city, r.country].filter(Boolean).join(", ") || "—"}{r.placed ? "" : " · not placed"}</span><span role="cell"><ConfidencePill confidence={r.confidence} /></span></button>)}
              </div>}
          {view === "list" && layers.posts && (posts?.pins.length || 0) > 100 && <nav className="results-pagination" aria-label="Map post list pages"><button className="button button-secondary button-small" disabled={!listPage} onClick={() => setListPage(listPage - 1)}>Previous posts</button><span>{listPage * 100 + 1}–{Math.min((listPage + 1) * 100, posts!.pins.length)} of {posts!.pins.length.toLocaleString()}</span><button className="button button-secondary button-small" disabled={(listPage + 1) * 100 >= posts!.pins.length} onClick={() => setListPage(listPage + 1)}>Next posts</button></nav>}
          {overlap && overlap.by_country.length > 0 && <details className="overlap-table"><summary>Overlap by country ({overlap.by_country.length})</summary>
            <table><thead><tr><th>Country</th><th>Subject</th><th>Reference</th><th>Subject near a reference</th><th>Share a recorded audience</th></tr></thead>
              <tbody>{overlap.by_country.map((c) => <tr key={c.country}><td>{c.country}</td><td>{c.subjects}</td><td>{c.references}</td><td>{c.subjects_near_reference}</td><td>{c.shared_audience_pairs}</td></tr>)}</tbody></table>
            <p className="footnote">{overlap.method}</p></details>}
        </div>

        {pickedTarget && !pickedPost && (
          <aside className="map-detail target-detail" aria-label="Selected target">
            <button className="inspector-close" onClick={() => setSelectedTarget("")} aria-label="Close">×</button>
            <h3>Posts about {pickedTarget.name}</h3>
            <div className="pill-row"><Pill tone="info">{pickedTarget.posts} post{pickedTarget.posts === 1 ? "" : "s"}</Pill>{pickedTarget.last_24h > 0 && <Pill tone="warn">{pickedTarget.last_24h} in the last 24 hours</Pill>}<Pill tone={pickedTarget.verified ? "ok" : "neutral"}>{pickedTarget.verified} verified</Pill></div>
            <p className="muted">Where posts are about, from places named in the text. Country-level unless a city is named.</p>
            <p><strong>Platforms</strong> {Object.entries(pickedTarget.platforms).map(([k, v]) => `${k} ${v}`).join(" · ")}<br /><strong>Languages</strong> {Object.entries(pickedTarget.languages).map(([k, v]) => `${k} ${v}`).join(" · ")}
              {Object.keys(pickedTarget.cities).length > 0 && <><br /><strong>Cities named</strong> {Object.entries(pickedTarget.cities).map(([k, v]) => `${k} ${v}`).join(" · ")}</>}</p>
            <ul className="post-list">{targetPosts.slice(0, 40).map((p) => <li key={p.item_id}><button className="button button-quiet button-small" onClick={() => { setSelectedTarget(""); setSelectedPost(p.item_id); }}><strong dir="auto">{p.author || "Unknown"}</strong> · <span dir="auto">{p.original_text.slice(0, 70)}</span></button></li>)}</ul>
            <button className="button button-secondary button-small" disabled={exporting || rangeError} onClick={() => void exportMapped(pickedTarget.name)}>Export these posts for analysis</button>
          </aside>)}
        {pickedPost && (
          <aside className="map-detail post-detail" aria-label="Selected post">
            <button className="inspector-close" onClick={() => setSelectedPost("")} aria-label="Close">×</button>
            <h3 dir="auto">{pickedPost.author || "Unknown author"}</h3>
            <p className="muted">{pickedPost.platform} · {pickedPost.published_at ? formatTime(pickedPost.published_at) : "date unknown"}</p>
            <div className="pill-row">{pickedPost.verified ? <Pill tone="ok">Verified by {pickedPost.verified_by || "a reviewer"}</Pill> : <Pill tone="warn">Not verified</Pill>}
              {pickedPost.inferred_location && <Pill tone="info" title={pickedPost.inferred_location.method}>Inferred: {pickedPost.inferred_location.name} · {Math.round(pickedPost.inferred_location.confidence * 100)}%</Pill>}</div>
            <div><strong>Original{pickedPost.language ? ` (${pickedPost.language})` : ""}</strong><p dir="auto" className="post-text">{pickedPost.original_text}</p></div>
            {pickedPost.translated_text && <div><strong>Translation</strong><p className="post-text">{pickedPost.translated_text}</p></div>}
            <p><strong>Posted from</strong> {pickedPost.origin ? `${pickedPost.origin.label} (${pickedPost.origin.kind})` : "Not known. The pin sits at a place the text names."}</p>
            {pickedPost.targets.length > 0 && <p><strong>About</strong> {pickedPost.targets.map((t) => t.city ? `${t.city}, ${t.name}` : t.name).join(", ")} <small className="muted">named in the text; country-level</small></p>}
            <div className="pill-row"><button className={`button ${pickedPost.verified ? "button-secondary" : "button-primary"} button-small`} onClick={() => void setVerified(pickedPost.item_id, !pickedPost.verified)}>{pickedPost.verified ? "✓ Verified. Undo" : "✓ Mark verified"}</button>
              {pickedPost.url && <a className="button button-quiet button-small" href={pickedPost.url} target="_blank" rel="noreferrer noopener">Open post</a>}</div>
          </aside>)}
        {picked && !pickedPost && !pickedTarget && (
          <aside className="map-detail" aria-label="Selected institution">
            <button className="inspector-close" onClick={() => setSelected("")} aria-label="Close">×</button>
            <h3 dir="auto">{picked.name}</h3>
            <p className="muted">{[picked.city, picked.country].filter(Boolean).join(", ")}{picked.network ? ` · ${picked.network}` : ""}</p>
            <div className="pill-row"><Pill tone={picked.status === "active" ? "ok" : "neutral"}>{titleCase(picked.status)}</Pill><ConfidencePill confidence={picked.confidence} />
              {picked.last_verified ? <Pill tone="ok">Verified {relativeTime(picked.last_verified)}</Pill> : <Pill tone="warn">Not verified</Pill>}</div>
            {picked.programs.length > 0 && <p><strong>Programs</strong> {picked.programs.map(titleCase).join(", ")}</p>}
            {picked.audiences.length > 0 && <p><strong>Audiences</strong> {picked.audiences.map(titleCase).join(", ")}</p>}
            <p><strong>Support</strong> {picked.source_count} source{picked.source_count === 1 ? "" : "s"} · {picked.activity.items} linked item{picked.activity.items === 1 ? "" : "s"}{picked.activity.recent_items ? ` (${picked.activity.recent_items} in the chosen window)` : ""}</p>
            {picked.location_precision && <p className="muted">Location precision: {picked.location_precision}</p>}
            {pickedOverlap?.nearest_reference && <p><strong>Nearest reference institution</strong> {pickedOverlap.nearest_reference.name} · {pickedOverlap.nearest_reference.distance_km} km{pickedOverlap.nearest_reference.same_city ? " · same city" : ""}
              {pickedOverlap.shared_audiences.length > 0 && <><br /><small className="muted">Both record: {pickedOverlap.shared_audiences.map(titleCase).join(", ")}</small></>}</p>}
            <button className="button button-primary" onClick={() => onOpenRecord(picked.entity_id)}>Open record and sources</button>
          </aside>)}
      </div>
    </section>
  );
}
