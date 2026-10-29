import { useEffect, useMemo, useState } from "react";
import { research } from "./research-api";
import type { NetworkCatalog, NetworkPreview, NetworkRow, PublicationSearchRow, SeedRow } from "./research-types";
import { Pill, Spinner, titleCase } from "./ui";

const FIELDS: Array<[string, string]> = [["name", "Name (required)"], ["city", "City"], ["country", "Country"], ["latitude", "Latitude"], ["longitude", "Longitude"], ["status", "Status"],
  ["audiences", "Audiences"], ["program_domains", "Programs"], ["source_url", "Source address"], ["entity_type", "Type"], ["address", "Address"]];

const toBase64 = (buffer: ArrayBuffer) => { let binary = ""; const bytes = new Uint8Array(buffer); for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000)); return btoa(binary); };
const PUBLICATION_PAGE_SIZE = 50;
const PUBLICATION_FILTERS = [
  ["all", "All results"], ["exact", "Exact date candidate"], ["relative", "Search age label"],
  ["page_date", "Date in result"], ["without_date", "Page without date"], ["no_page", "No relevant page"],
] as const;

function exportPublicationAudit(rows: PublicationSearchRow[]) {
  const fields = ["entity_id", "name", "city", "country", "network", "checked_on", "result",
    "exact_publication_date_candidate", "exact_date_basis", "date_shown_in_result", "search_age_label",
    "evidence_scope", "match_strength", "evidence_title", "evidence_url", "query", "fallback_query",
    "other_candidate_sources", "interpretation"];
  const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const lines = [fields.map(escape).join(","), ...rows.map((row) => {
    const otherSources = row.candidates.filter((candidate) => candidate.url && candidate.url !== row.evidence_url)
      .map((candidate) => ({ title: candidate.title, url: candidate.url, date: candidate.publication_date || candidate.page_date_candidate,
        age: candidate.search_age_label, scope: candidate.source_scope }));
    return [row.entity_id, row.name, row.city, row.country, row.network, row.checked_on, row.result,
      row.exact_publication_date, row.date_basis, row.date_shown_in_result, row.search_age_label,
      row.evidence_scope, row.match_strength, row.evidence_title, row.evidence_url, row.query, row.fallback_query,
      JSON.stringify(otherSources), "Search evidence only; does not confirm the location’s latest own post or current operating status."]
      .map(escape).join(",");
  })];
  const blob = new Blob(["\uFEFF", lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = `team4-publication-search-audit-${rows[0]?.checked_on || "catalog"}.csv`;
  document.body.appendChild(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

const publicationResultLabel = (result: string) => ({
  dated_or_relative_signal: "Page with a date or age signal",
  relevant_page_without_date: "Relevant page without a date",
  no_relevant_dated_result: "No relevant page found",
}[result] || titleCase(result.replaceAll("_", " ")));
const publicationScopeLabel = (scope: string) => ({
  official_or_host: "Official or host source",
  third_party_or_unclear: "Third-party or unclear source",
  social_or_platform: "Social or platform result",
}[scope] || scope);

/** Networks, reference directories, and open-data seeds. Nothing is imported until a person confirms the mapping or the rows. */
export function NetworksPanel({ projectId, onClose, onChanged, onError }: { projectId: string; onClose: () => void; onChanged: () => void; onError: (m: string) => void }) {
  const [tab, setTab] = useState<"networks" | "catalog" | "import" | "seed">("networks");
  const [networks, setNetworks] = useState<NetworkRow[]>([]);
  const [catalog, setCatalog] = useState<NetworkCatalog | null>(null);
  const [selectedCatalog, setSelectedCatalog] = useState<Record<string, boolean>>({ confucius_institutes: true, luban_workshops: true, american_spaces: true });
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
  const [publicationQuery, setPublicationQuery] = useState("");
  const [publicationFilter, setPublicationFilter] = useState<string>("all");
  const [publicationPage, setPublicationPage] = useState(0);

  const reload = () => research.networks(projectId).then(setNetworks).catch(() => undefined);
  useEffect(() => { void reload(); }, [projectId]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (tab !== "catalog") return;
    void research.teamCatalog(projectId).then((result) => {
      setCatalog(result);
      setSelectedCatalog((current) => Object.keys(current).length ? current : Object.fromEntries(result.networks.filter((n) => n.default_selected).map((n) => [n.id, true])));
    }).catch((e) => onError(e instanceof Error ? e.message : String(e)));
  }, [tab, projectId]);
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
  const importCatalog = () => guard("catalogimport", async () => {
    const chosen = Object.entries(selectedCatalog).filter(([, enabled]) => enabled).map(([id]) => id);
    const result = await research.importTeamCatalog(projectId, chosen);
    setMessage(`Added ${result.added.toLocaleString()} records from ${result.selected_records.toLocaleString()} selected catalog rows; ${result.skipped_existing.toLocaleString()} were already present. ${result.note}`);
    await reload(); onChanged();
  });
  const publicationRows = catalog?.publication_audit.records || [];
  const filteredPublicationRows = useMemo(() => {
    const query = publicationQuery.trim().toLocaleLowerCase();
    return publicationRows.filter((row) => {
      const filterMatch = publicationFilter === "all"
        || (publicationFilter === "exact" && Boolean(row.exact_publication_date))
        || (publicationFilter === "relative" && Boolean(row.search_age_label))
        || (publicationFilter === "page_date" && Boolean(row.date_shown_in_result))
        || (publicationFilter === "without_date" && row.result === "relevant_page_without_date")
        || (publicationFilter === "no_page" && row.result === "no_relevant_dated_result");
      if (!filterMatch || !query) return filterMatch;
      return [row.name, row.city, row.country, row.network_label, row.evidence_title, row.evidence_url, row.query]
        .some((value) => value.toLocaleLowerCase().includes(query));
    });
  }, [publicationRows, publicationQuery, publicationFilter]);
  const publicationPageCount = Math.max(1, Math.ceil(filteredPublicationRows.length / PUBLICATION_PAGE_SIZE));
  const currentPublicationRows = filteredPublicationRows.slice(publicationPage * PUBLICATION_PAGE_SIZE, (publicationPage + 1) * PUBLICATION_PAGE_SIZE);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="modal candidates-panel" role="dialog" aria-modal="true" aria-labelledby="net-title" onClick={(event) => event.stopPropagation()}>
        <header className="modal-head"><div><span className="eyebrow">NETWORKS</span><h2 id="net-title">Networks and reference directories</h2></div><button className="text-button" onClick={onClose}>Close</button></header>
        <div className="tabs" role="tablist" aria-label="Network tools" style={{ padding: "0 1.2rem" }}>
          {([["networks", "Your networks"], ["catalog", "Built-in team catalog"], ["import", "Import a directory"], ["seed", "Search open data"]] as const).map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{label}</button>)}
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

          {tab === "catalog" && <>
            <p>{catalog?.use_note || "Load the bundled Team 4 database into this project as reusable institution networks."}</p>
            {!catalog && <div className="loading-block"><Spinner /> Loading the built-in catalog…</div>}
            {catalog && <>
              <p className="muted">Select the three core networks for comparison. Supplemental lists stay unchecked until you choose them.</p>
              <ul className="candidate-list">{catalog.networks.map((item) => (
                <li key={item.id}><label className="check-row">
                  <input type="checkbox" checked={Boolean(selectedCatalog[item.id])} disabled={busy === "catalogimport"}
                    onChange={(e) => setSelectedCatalog({ ...selectedCatalog, [item.id]: e.target.checked })} />
                  <span><strong>{item.label}</strong><small className="muted">{item.records.toLocaleString()} records · {item.placed.toLocaleString()} with coordinates · {item.source}</small><small className="muted">Map labels: {item.status_counts.active.toLocaleString()} active · {item.status_counts.closed.toLocaleString()} closed · {item.status_counts.unknown.toLocaleString()} unknown</small><small className="muted">{item.summary}</small></span>
                </label></li>))}</ul>
              <div className="preview-actions"><button className="button button-primary" disabled={!Object.values(selectedCatalog).some(Boolean) || busy === "catalogimport"} onClick={() => void importCatalog()}>
                {busy === "catalogimport" ? <><Spinner /> Adding catalog…</> : "Add selected datasets to this project"}
              </button><small>Imported status follows the original workbook label as a working assumption. The raw label stays attached as evidence and is not independently verified.</small></div>
              <details className="help-disclosure"><summary>Overlap leads, data checks, and activity pulse</summary>
                <p className="footnote">The workbook contains {catalog.overlap_claim_counts.ci_american_spaces ?? 0} CI–American Space assertions and {catalog.overlap_claim_counts.luban_american_spaces_detail_workbook ?? 0} Luban–American Space assertions in the detailed overlap list. These are team-reported leads; exported map distances are recalculated from the coordinates.</p>
                <ul>{catalog.data_quality_notes.map((note, index) => <li key={index}>{note}</li>)}</ul>
                <h3>Record-level activity audit</h3>
                <p className="footnote">The original lists contain {catalog.activity_audit.core_records.toLocaleString()} core records and {catalog.activity_audit.supplementary_records.toLocaleString()} supplementary leads, with {catalog.activity_audit.core_records_with_last_post_date + catalog.activity_audit.supplementary_records_with_last_post_date} explicit last-post dates supplied. {catalog.activity_audit.named_site_checks} separate named-site spot checks were made; {catalog.activity_audit.named_site_checks_with_dated_signals} had dated event or notice signals. {catalog.activity_audit.interpretation}</p>
                <ul>{Object.entries(catalog.activity_audit.source_status_claim_counts).map(([name, claims]) => <li key={name}><strong>{name} source labels:</strong> {Object.entries(claims).map(([claim, count]) => `${claim} ${count}`).join(" · ")}</li>)}</ul>
                <h3>Public-source pulse checked {catalog.as_of}</h3>
                <ul>{catalog.activity_pulse.map((pulse) => <li key={pulse.network}><strong>{pulse.network}:</strong> {pulse.status} <a href={pulse.source_url} target="_blank" rel="noreferrer">Source ↗</a><small className="muted">{pulse.signal}</small></li>)}</ul>
                {catalog.site_activity_spot_checks.length > 0 && <>
                  <h3>Named-site activity spot checks</h3>
                  <p className="footnote">Selected public signals, not a representative sample. Event reports and cadence claims do not establish current operating status or posting frequency.</p>
                  <ul>{catalog.site_activity_spot_checks.map((check) => <li key={check.entity_id}>
                    <strong>{check.entity_name}</strong> ({check.country}) — {check.assessment}
                    <ul>{check.signals.map((signal, index) => <li key={`${check.entity_id}-${index}`}>
                      <strong>{signal.date || "Undated"} · {signal.kind}:</strong> {signal.note} <a href={signal.source_url} target="_blank" rel="noreferrer">{signal.source_title} ↗</a>
                      {signal.related_sources?.map((source) => <span key={source.url}> · <a href={source.url} target="_blank" rel="noreferrer">{source.title} ↗</a></span>)}
                      <small className="muted">Source quality: {signal.source_quality}</small>
                    </li>)}</ul>
                  </li>)}</ul>
                </>}
                <h3>Row-by-row public publication search</h3>
                <p className="footnote">Searched {catalog.publication_audit.rows_searched.toLocaleString()} catalog rows on {catalog.publication_audit.checked_on}: {catalog.publication_audit.exact_publication_date_candidate.toLocaleString()} exact publication-date candidates, {catalog.publication_audit.relative_search_age_label.toLocaleString()} relative search-age labels, and {catalog.publication_audit.no_relevant_result.toLocaleString()} rows without a relevant page. Counts overlap. A date in a snippet can be an event date, and an indexed page may be a host or third-party report rather than the institution’s own latest post. No registry activity status was changed.</p>
                <details className="help-disclosure publication-audit-disclosure">
                  <summary>Inspect all {catalog.publication_audit.rows_searched.toLocaleString()} row-level search results and export CSV</summary>
                  <p className="footnote">{catalog.publication_audit.method} {catalog.publication_audit.caveat}</p>
                  <div className="toolbar publication-audit-toolbar">
                    <div className="search-field"><input value={publicationQuery} onChange={(event) => { setPublicationQuery(event.target.value); setPublicationPage(0); }} placeholder="Search institution, place, source, or query" aria-label="Filter publication search results" /></div>
                    <select value={publicationFilter} onChange={(event) => { setPublicationFilter(event.target.value); setPublicationPage(0); }} aria-label="Filter publication result type">
                      {PUBLICATION_FILTERS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                    <button className="button" onClick={() => exportPublicationAudit(publicationRows)}>Download full audit CSV ({publicationRows.length.toLocaleString()} rows)</button>
                  </div>
                  <p className="muted" role="status">Showing {filteredPublicationRows.length ? publicationPage * PUBLICATION_PAGE_SIZE + 1 : 0}–{Math.min((publicationPage + 1) * PUBLICATION_PAGE_SIZE, filteredPublicationRows.length)} of {filteredPublicationRows.length.toLocaleString()} matching rows. “Exact” means the date was exposed in publication metadata or a date-coded URL; it is still a candidate.</p>
                  <div className="publication-audit-scroll">
                    <table className="data-table publication-audit-table">
                      <thead><tr><th>Institution</th><th>Publication signals</th><th>Search evidence</th></tr></thead>
                      <tbody>{currentPublicationRows.map((row) => {
                        const otherCandidates = row.candidates.filter((candidate) => candidate.url && candidate.url !== row.evidence_url);
                        return <tr key={row.entity_id}>
                          <td><strong>{row.name}</strong><small className="muted">{row.network_label} · {[row.city, row.country].filter(Boolean).join(", ") || "Place not specified"}</small><small className="muted">{publicationResultLabel(row.result)}</small></td>
                          <td>{row.exact_publication_date ? <small><strong>Exact date candidate:</strong> {row.exact_publication_date} ({row.date_basis || "publication metadata"})</small> : <small><strong>Exact date candidate:</strong> none</small>}
                            {row.date_shown_in_result && <small><strong>Date shown in result:</strong> {row.date_shown_in_result}</small>}
                            {row.search_age_label && <small><strong>Search-age label:</strong> {row.search_age_label}</small>}
                          </td>
                          <td>{row.evidence_url ? <a href={row.evidence_url} target="_blank" rel="noopener noreferrer">{row.evidence_title || row.evidence_url} ↗</a> : <span className="muted">No relevant source selected</span>}
                            {row.evidence_scope && <small className="muted">{publicationScopeLabel(row.evidence_scope)} · {row.match_strength.replaceAll("_", " ")}</small>}
                            {otherCandidates.length > 0 && <details><summary>{otherCandidates.length} alternate source{otherCandidates.length === 1 ? "" : "s"}</summary><ul>{otherCandidates.map((candidate) => <li key={candidate.url}><a href={candidate.url} target="_blank" rel="noopener noreferrer">{candidate.title || candidate.url} ↗</a><small className="muted">{candidate.publication_date || candidate.page_date_candidate || candidate.search_age_label || "No visible date"} · {publicationScopeLabel(candidate.source_scope)}</small></li>)}</ul></details>}
                            <details><summary>Search query</summary><code className="publication-audit-query">{row.query}</code>{row.fallback_query && <code className="publication-audit-query">Alternate-name search: {row.fallback_query}</code>}</details>
                          </td>
                        </tr>;
                      })}</tbody>
                    </table>
                  </div>
                  {filteredPublicationRows.length > PUBLICATION_PAGE_SIZE && <div className="results-pagination"><button className="button" disabled={publicationPage === 0} onClick={() => setPublicationPage((page) => Math.max(0, page - 1))}>Previous</button><span>Page {publicationPage + 1} of {publicationPageCount}</span><button className="button" disabled={publicationPage + 1 >= publicationPageCount} onClick={() => setPublicationPage((page) => Math.min(publicationPageCount - 1, page + 1))}>Next</button></div>}
                </details>
                {catalog.program_overlap_interpretations.length > 0 && <details className="help-disclosure">
                  <summary>Team program and messaging hypotheses ({catalog.program_overlap_interpretations.length})</summary>
                  <p className="footnote">These are the source team’s interpretations of overlap and messaging themes. They are research leads, not independently verified findings.</p>
                  <ul>{catalog.program_overlap_interpretations.map((item) => <li key={item.program_type}>
                    <strong>{item.program_type}</strong> — {item.overlap_assessment}
                    <small className="muted">American Spaces counterpart: {item.american_spaces_counterpart}</small>
                    <small className="muted">Team interpretation: {item.team_judgment}</small>
                    <small className="muted">Regions: {item.strongest_regions} · Search-term IDs: {item.niche_term_ids}</small>
                    {item.source_origin.sheet && <small className="muted">Source: {item.source_origin.file} · {item.source_origin.sheet} · row {item.source_origin.row}</small>}
                  </li>)}</ul>
                </details>}
                <p className="footnote">The complete search-term workbook, raw source mentions, and team overlap claims are retained in references/team4_network_catalog.json after import. Six selected search suggestions are available in the research plan editor.</p>
              </details>
            </>}
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
