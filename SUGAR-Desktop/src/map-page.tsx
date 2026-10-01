import { useCallback, useEffect, useMemo, useState } from "react";
import { research } from "./research-api";
import type { Institution, InstitutionList, NetworkRow, OverlapResult, PostMap } from "./research-types";
import { NetworkMap, type Basemap, type Line, type MapMode, type PostLayers } from "./network-map";
import { ConfidencePill } from "./institutions-page";
import { EmptyState, Pill, Spinner, formatTime, relativeTime, titleCase } from "./ui";

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
  const [posts, setPosts] = useState<PostMap | null>(null);
  const [basemap, setBasemap] = useState<Basemap>(dark ? "dark" : "streets");
  const [layers, setLayers] = useState<PostLayers>({ posts: true, targets: true, flows: false, institutions: true });
  const [selectedPost, setSelectedPost] = useState("");
  const [verdictFilter, setVerdictFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const [list, nets, pm] = await Promise.all([research.institutions(projectId, { status, confidence: level, country, program, audience, since: sinceDate(windowKey) }), research.networks(projectId),
        research.postMap(projectId, { verdict: verdictFilter }).catch(() => null)]);
      setData(list); setNetworks(nets); setPosts(pm);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setLoading(false); }
  }, [projectId, status, level, country, program, audience, windowKey, verdictFilter]);
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
          <p>Markers come from verified-or-pending records, each one open to its sources. Distances are computed from recorded coordinates; they are not findings of influence.</p></div>
        <div className="run-controls">
          <div className="segmented" role="radiogroup" aria-label="View">{(["map", "list"] as const).map((v) => <button key={v} role="radio" aria-checked={view === v} className={view === v ? "on" : ""} onClick={() => setView(v)}>{titleCase(v)}</button>)}</div>
          <button className="button button-secondary" onClick={onOpenInstitutions}>Institutions</button>
        </div>
      </div>
      {error && <div className="notice notice-warn" role="alert">{error}</div>}

      <div className="map-layout">
        <aside className="map-filters" aria-label="Map filters">
          <div className="field-block"><span>Layers</span>
            <label className="check-row"><input type="checkbox" checked={layers.posts} onChange={(e) => setLayers({ ...layers, posts: e.target.checked })} /><span><span className="swatch post" aria-hidden="true" /> Posts <small className="muted">{posts?.pins.length ?? 0}</small></span></label>
            <label className="check-row"><input type="checkbox" checked={layers.targets} onChange={(e) => setLayers({ ...layers, targets: e.target.checked })} /><span><span className="swatch target" aria-hidden="true" /> Targets: where posts are about <small className="muted">{posts?.targets.length ?? 0}</small></span></label>
            <label className="check-row"><input type="checkbox" checked={layers.flows} onChange={(e) => setLayers({ ...layers, flows: e.target.checked })} /><span>Origin → target lines</span></label>
            <label className="check-row"><input type="checkbox" checked={layers.institutions} onChange={(e) => setLayers({ ...layers, institutions: e.target.checked })} /><span>Institutions</span></label>
            <label className="field-block"><span>Posts</span><select value={verdictFilter} onChange={(e) => setVerdictFilter(e.target.value)}><option value="">All posts</option><option value="relevant">Verified only</option><option value="none">Not yet checked</option></select></label></div>
          <div className="field-block"><span>Basemap</span>
            <div className="segmented" role="radiogroup" aria-label="Basemap">{(["dark", "streets", "terrain"] as const).map((v) => <button key={v} role="radio" aria-checked={basemap === v} className={basemap === v ? "on" : ""} onClick={() => setBasemap(v)}>{titleCase(v)}</button>)}</div></div>
          <div className="field-block"><span>Networks</span>
            {networks.length === 0 && <small className="muted">No networks yet. Import a directory on the Institutions page.</small>}
            {networks.map((n) => <label key={n.name || "none"} className="check-row"><input type="checkbox" checked={!hidden[n.name]} onChange={(e) => setHidden({ ...hidden, [n.name]: !e.target.checked })} />
              <span><span className={`swatch ${n.role}`} aria-hidden="true" /> {n.label} <small className="muted">{n.institutions}</small></span></label>)}</div>
          <label className="field-block"><span>Evidence from</span><select value={windowKey} onChange={(e) => setWindowKey(e.target.value)}>{WINDOWS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
          <label className="field-block"><span>Status</span><select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Any</option>{["active", "closed", "renamed", "relocated", "unknown"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</select></label>
          <label className="field-block"><span>Confidence</span><select value={level} onChange={(e) => setLevel(e.target.value)}><option value="">Any</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
          <label className="field-block"><span>Country</span><select value={country} onChange={(e) => setCountry(e.target.value)}><option value="">All</option>{data?.facets.countries.map((f) => <option key={f.key} value={f.key === "unknown" ? "" : f.key}>{f.key} ({f.count})</option>)}</select></label>
          <label className="field-block"><span>Program</span><select value={program} onChange={(e) => setProgram(e.target.value)}><option value="">Any</option>{data?.facets.programs.map((f) => <option key={f.key} value={f.key}>{titleCase(f.key)} ({f.count})</option>)}</select></label>
          <label className="field-block"><span>Audience</span><select value={audience} onChange={(e) => setAudience(e.target.value)}><option value="">Any</option>{data?.facets.audiences.map((f) => <option key={f.key} value={f.key}>{titleCase(f.key)} ({f.count})</option>)}</select></label>
          <div className="field-block"><span>Map style</span>
            <div className="segmented" role="radiogroup" aria-label="Map style">{([["points", "Points"], ["heat", "Activity heat"]] as const).map(([v, l]) => <button key={v} role="radio" aria-checked={mode === v} className={mode === v ? "on" : ""} onClick={() => setMode(v)}>{l}</button>)}</div>
            <small className="muted">Heat reflects recent linked items and recorded programs for the subject network, not a measure of influence.</small></div>
          {references.length > 0 && subjects.length > 0 && <div className="field-block"><label className="check-row"><input type="checkbox" checked={showLines} onChange={(e) => setShowLines(e.target.checked)} /><span>Link each subject to its nearest reference within</span></label>
            <select value={nearKm} onChange={(e) => setNearKm(Number(e.target.value))} aria-label="Distance"><option value={5}>5 km</option><option value={25}>25 km</option><option value={100}>100 km</option><option value={250}>250 km</option></select></div>}
        </aside>

        <div className="map-main">
          <div className="map-stats" role="status">
            {loading && <Spinner />}<strong>{visible.filter((r) => r.placed).length}</strong> on the map · <strong>{data?.unplaced ?? 0}</strong> not placed · <strong>{posts?.pins.length ?? 0}</strong> posts
            {overlap && <> · <strong>{near}</strong> subject institutions have a reference institution within {nearKm} km</>}
          </div>
          {view === "map" ? <NetworkMap rows={visible} networks={networks} mode={mode} lines={lines} selectedId={selected} onSelect={(id) => { setSelectedPost(""); setSelected(id); }} basemap={basemap}
            posts={posts} layers={layers} selectedPost={selectedPost} onSelectPost={(id) => { setSelected(""); setSelectedPost(id); }} />
            : <div className="project-table" role="table" aria-label="Institutions on the map">
                <div className="project-table-head" role="row"><span role="columnheader">Institution</span><span role="columnheader">Status</span><span role="columnheader">Where</span><span role="columnheader">Support</span></div>
                {layers.posts && (posts?.pins || []).map((p) => <button key={p.item_id} className="project-row" role="row" onClick={() => { setSelected(""); setSelectedPost(p.item_id); }}><span role="cell"><strong dir="auto">{p.author || "Unknown author"}</strong> <small className="muted">{p.platform} · post</small></span>
                  <span role="cell">{p.verified ? "Verified" : "Not verified"}</span><span role="cell">{p.origin ? p.origin.label : p.inferred_location ? `About ${p.inferred_location.name}` : "—"}</span><span role="cell"><small dir="auto">{p.original_text.slice(0, 80)}</small></span></button>)}
                {visible.map((r) => <button key={r.entity_id} className="project-row" role="row" onClick={() => setSelected(r.entity_id)}><span role="cell"><strong dir="auto">{r.name}</strong> <small className="muted">{r.network}</small></span>
                  <span role="cell">{titleCase(r.status)}</span><span role="cell">{[r.city, r.country].filter(Boolean).join(", ") || "—"}{r.placed ? "" : " · not placed"}</span><span role="cell"><ConfidencePill confidence={r.confidence} /></span></button>)}
              </div>}
          {overlap && overlap.by_country.length > 0 && <details className="overlap-table"><summary>Overlap by country ({overlap.by_country.length})</summary>
            <table><thead><tr><th>Country</th><th>Subject</th><th>Reference</th><th>Subject near a reference</th><th>Share a recorded audience</th></tr></thead>
              <tbody>{overlap.by_country.map((c) => <tr key={c.country}><td>{c.country}</td><td>{c.subjects}</td><td>{c.references}</td><td>{c.subjects_near_reference}</td><td>{c.shared_audience_pairs}</td></tr>)}</tbody></table>
            <p className="footnote">{overlap.method}</p></details>}
        </div>

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
            {pickedPost.targets.length > 0 && <p><strong>About</strong> {pickedPost.targets.map((t) => t.name).join(", ")} <small className="muted">named in the text; country-level</small></p>}
            <div className="pill-row"><button className={`button ${pickedPost.verified ? "button-secondary" : "button-primary"} button-small`} onClick={() => void setVerified(pickedPost.item_id, !pickedPost.verified)}>{pickedPost.verified ? "✓ Verified. Undo" : "✓ Mark verified"}</button>
              {pickedPost.url && <a className="button button-quiet button-small" href={pickedPost.url} target="_blank" rel="noreferrer noopener">Open post</a>}</div>
          </aside>)}
        {picked && !pickedPost && (
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
