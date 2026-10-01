import { useEffect, useState } from "react";
import { research } from "./research-api";
import type { NetworkPreview, NetworkRow, SeedRow } from "./research-types";
import { Pill, Spinner, titleCase } from "./ui";

const FIELDS: Array<[string, string]> = [["name", "Name (required)"], ["city", "City"], ["country", "Country"], ["latitude", "Latitude"], ["longitude", "Longitude"], ["status", "Status"],
  ["audiences", "Audiences"], ["program_domains", "Programs"], ["source_url", "Source address"], ["entity_type", "Type"], ["address", "Address"]];

const toBase64 = (buffer: ArrayBuffer) => { let binary = ""; const bytes = new Uint8Array(buffer); for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000)); return btoa(binary); };

/** Networks, reference directories, and open-data seeds. Nothing is imported until a person confirms the mapping or the rows. */
export function NetworksPanel({ projectId, onClose, onChanged, onError }: { projectId: string; onClose: () => void; onChanged: () => void; onError: (m: string) => void }) {
  const [tab, setTab] = useState<"networks" | "import" | "seed">("networks");
  const [networks, setNetworks] = useState<NetworkRow[]>([]);
  const [busy, setBusy] = useState("");
  const [preview, setPreview] = useState<NetworkPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [network, setNetwork] = useState("");
  const [role, setRole] = useState<"subject" | "reference">("reference");
  const [coverage, setCoverage] = useState("");
  const [license, setLicense] = useState("");
  const [partial, setPartial] = useState(false);
  const [message, setMessage] = useState("");
  const [source, setSource] = useState<"wikidata" | "osm">("wikidata");
  const [term, setTerm] = useState("");
  const [country, setCountry] = useState("");
  const [rows, setRows] = useState<SeedRow[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});

  const reload = () => research.networks(projectId).then(setNetworks).catch(() => undefined);
  useEffect(() => { void reload(); }, [projectId]);   // eslint-disable-line react-hooks/exhaustive-deps
  const guard = async (label: string, work: () => Promise<void>) => { setBusy(label); setMessage(""); try { await work(); } catch (e) { onError(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); } };

  const choose = (file: File | undefined) => file && guard("preview", async () => {
    const result = await research.previewNetworkFile(projectId, file.name, toBase64(await file.arrayBuffer()));
    setPreview(result); setMapping(result.suggested_mapping || {}); if (!network) setNetwork(file.name.replace(/\.[^.]+$/, ""));
  });
  const columns = preview?.sample?.[0] ? Object.keys(preview.sample[0]) : Object.values(preview?.suggested_mapping || {});
  const doImport = () => guard("import", async () => {
    await research.importNetworkFile(projectId, { file_id: preview!.file_id, mapping: Object.fromEntries(Object.entries(mapping).filter(([, v]) => v)), network, role, dataset_name: preview!.filename,
      known_coverage_limits: coverage, license_notes: license, accept_partial: partial });
    setMessage(`Imported ${preview!.valid_rows} institutions into “${network}”.`); setPreview(null); await reload(); onChanged();
  });
  const search = () => guard("seed", async () => { setRows(await research.seedSearch(projectId, source, term, country)); setPicked({}); });
  const importSeeds = () => guard("seedimport", async () => {
    const chosen = rows.filter((r) => picked[r.seed_id]);
    const result = await research.seedImport(projectId, chosen, network, role);
    setMessage(`Recorded ${result.imported.length} unreviewed institutions in “${network}”. Verify them on the Institutions page.`); setRows([]); await reload(); onChanged();
  });

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="modal candidates-panel" role="dialog" aria-modal="true" aria-labelledby="net-title" onClick={(event) => event.stopPropagation()}>
        <header className="modal-head"><div><span className="eyebrow">NETWORKS</span><h2 id="net-title">Networks and reference directories</h2></div><button className="text-button" onClick={onClose}>Close</button></header>
        <div className="tabs" role="tablist" aria-label="Network tools" style={{ padding: "0 1.2rem" }}>
          {([["networks", "Your networks"], ["import", "Import a directory"], ["seed", "Search open data"]] as const).map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{label}</button>)}
        </div>
        <div className="modal-body">
          {message && <div className="notice notice-ok" role="status">{message}</div>}
          {tab === "networks" && <>
            <p>A <strong>subject</strong> network is the one you are studying. A <strong>reference</strong> network is one to compare against, such as a government's own centers. The overlap view and the map use these roles.</p>
            {networks.length === 0 && <p className="muted">No networks yet. Import a directory or search open data to create one.</p>}
            <ul className="candidate-list">{networks.map((n) => (
              <li key={n.name || "unassigned"}><div><strong>{n.label}</strong><small className="muted">{n.institutions} institutions · {n.placed} on the map</small></div>
                {n.name ? <select value={n.role} onChange={(e) => void guard("role", async () => { setNetworks(await research.setNetwork(projectId, n.name, e.target.value as "subject" | "reference", n.label)); onChanged(); })} aria-label={`Role of ${n.label}`}>
                  <option value="subject">Subject</option><option value="reference">Reference</option></select> : <Pill>Unassigned</Pill>}</li>))}</ul>
          </>}

          {tab === "import" && <>
            <p>Import a published directory (CSV, TSV, JSON, GeoJSON or Excel). You confirm which column is which before anything is recorded, and every row keeps the file it came from.</p>
            <label className="field-block"><span>File</span><input type="file" accept=".csv,.tsv,.json,.jsonl,.geojson,.xlsx" onChange={(event) => choose(event.currentTarget.files?.[0])} aria-label="Directory file" /></label>
            {busy === "preview" && <div className="loading-block"><Spinner /> Reading the file…</div>}
            {preview && <>
              <p className="muted" role="status">{preview.row_count} rows · {preview.valid_rows} valid{preview.error_count ? ` · ${preview.error_count} with problems` : ""}</p>
              {preview.errors.slice(0, 3).map((e) => <div key={e} className="notice notice-warn">{e}</div>)}
              <div className="field-grid">{FIELDS.map(([key, label]) => (
                <label className="field-block" key={key}><span>{label}</span>
                  <select value={mapping[key] || ""} onChange={(e) => setMapping({ ...mapping, [key]: e.target.value })}><option value="">— not in the file —</option>{columns.map((c) => <option key={c} value={c}>{c}</option>)}</select></label>))}</div>
              <div className="field-grid">
                <label className="field-block"><span>Network name <em>Required</em></span><input value={network} onChange={(e) => setNetwork(e.target.value)} /></label>
                <label className="field-block"><span>Role</span><select value={role} onChange={(e) => setRole(e.target.value as "subject" | "reference")}><option value="reference">Reference (to compare against)</option><option value="subject">Subject (being studied)</option></select></label>
                <label className="field-block"><span>What the directory does not cover</span><input value={coverage} onChange={(e) => setCoverage(e.target.value)} placeholder="Known gaps or limits" /></label>
                <label className="field-block"><span>License or terms</span><input value={license} onChange={(e) => setLicense(e.target.value)} placeholder="e.g. public domain" /></label></div>
              {preview.error_count > 0 && <label className="check-row"><input type="checkbox" checked={partial} onChange={(e) => setPartial(e.target.checked)} /><span>Import the valid rows and skip the {preview.error_count} with problems</span></label>}
              <div className="preview-actions"><button className="button button-primary" disabled={!mapping.name || !network.trim() || busy === "import" || (preview.error_count > 0 && !partial)} onClick={() => void doImport()}>{busy === "import" ? <><Spinner /> Importing…</> : "Import"}</button></div></>}
          </>}

          {tab === "seed" && <>
            <p>Find candidates in Wikidata or OpenStreetMap. These are community-edited starting points: each one you choose is recorded as unreviewed and cites its page.</p>
            <div className="toolbar">
              <select value={source} onChange={(e) => setSource(e.target.value as "wikidata" | "osm")} aria-label="Open data source"><option value="wikidata">Wikidata</option><option value="osm">OpenStreetMap</option></select>
              <div className="search-field"><input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Name or type, e.g. cultural center" aria-label="Search term" onKeyDown={(e) => { if (e.key === "Enter" && term.trim().length > 2) void search(); }} /></div>
              {source === "osm" && <input className="short-input" value={country} onChange={(e) => setCountry(e.target.value.toUpperCase().slice(0, 2))} placeholder="Country code" aria-label="Country code" />}
              <button className="button button-primary" disabled={term.trim().length < 3 || busy === "seed"} onClick={() => void search()}>{busy === "seed" ? <><Spinner /> Searching…</> : "Search"}</button>
            </div>
            {rows.length > 0 && <>
              <ul className="candidate-list">{rows.map((r) => (
                <li key={r.seed_id}><label className="check-row"><input type="checkbox" checked={Boolean(picked[r.seed_id])} onChange={(e) => setPicked({ ...picked, [r.seed_id]: e.target.checked })} />
                  <span><strong dir="auto">{r.name}</strong>{r.description && <small className="muted"> {r.description}</small>}<br /><small className="muted">{[r.city, r.country].filter(Boolean).join(", ")}{r.latitude !== null ? " · has coordinates" : ""}{r.closed_date ? ` · ended ${r.closed_date}` : ""} · <a href={r.source_url} target="_blank" rel="noreferrer">{titleCase(r.seed_source)} ↗</a></small></span></label></li>))}</ul>
              <div className="field-grid">
                <label className="field-block"><span>Network name <em>Required</em></span><input value={network} onChange={(e) => setNetwork(e.target.value)} /></label>
                <label className="field-block"><span>Role</span><select value={role} onChange={(e) => setRole(e.target.value as "subject" | "reference")}><option value="subject">Subject (being studied)</option><option value="reference">Reference (to compare against)</option></select></label></div>
              <div className="preview-actions"><button className="button button-primary" disabled={!network.trim() || !rows.some((r) => picked[r.seed_id]) || busy === "seedimport"} onClick={() => void importSeeds()}>Record chosen</button></div></>}
          </>}
        </div>
      </section>
    </div>
  );
}
