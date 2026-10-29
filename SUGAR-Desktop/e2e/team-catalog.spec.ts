import { expect, test, type Page } from "@playwright/test";
import type { Institution, NetworkCatalog, NetworkRow, OverlapResult } from "../src/research-types";

const projectId = "00000000-0000-4000-8000-000000000004";
const headers = { "access-control-allow-origin": "http://127.0.0.1:1420", "access-control-allow-methods": "GET, POST, DELETE, OPTIONS", "access-control-allow-headers": "authorization, content-type" };

const datasets: NetworkCatalog["networks"] = [
  { id: "confucius_institutes", network: "team4_confucius_institutes", label: "Confucius Institutes · Team 4", role: "subject", color: "#a23b35", records: 586, placed: 586, status_counts: { active: 586, closed: 0, unknown: 0 }, source: "CI workbook", summary: "Main CI directory", default_selected: true },
  { id: "luban_workshops", network: "team4_luban_workshops", label: "Luban Workshops · Team 4", role: "subject", color: "#d17a22", records: 38, placed: 37, status_counts: { active: 36, closed: 1, unknown: 1 }, source: "Luban workbook", summary: "Detailed locations", default_selected: true },
  { id: "american_spaces", network: "team4_american_spaces", label: "American Spaces · Team 4", role: "reference", color: "#267293", records: 559, placed: 559, status_counts: { active: 536, closed: 23, unknown: 0 }, source: "American Spaces workbook", summary: "Directory locations", default_selected: true },
  { id: "ci_location_leads", network: "team4_ci_location_leads", label: "CI location leads · Team 4", role: "subject", color: "#aa5a54", records: 41, placed: 32, status_counts: { active: 7, closed: 25, unknown: 9 }, source: "CI location workbook", summary: "Unmatched or ambiguous rows", default_selected: false },
  { id: "luban_active_list", network: "team4_luban_active_list", label: "Luban active-list entries · Team 4", role: "subject", color: "#da9c56", records: 40, placed: 0, status_counts: { active: 40, closed: 0, unknown: 0 }, source: "Luban list", summary: "Unlocated supplemental list", default_selected: false },
  { id: "ci_closure_leads", network: "team4_ci_closure_leads", label: "Selected CI closure leads · Team 4", role: "subject", color: "#7b5b71", records: 27, placed: 27, status_counts: { active: 0, closed: 23, unknown: 4 }, source: "CI closure workbook", summary: "Selected closure examples", default_selected: false },
];

function institution(entityId: string, name: string, network: string, status: string, claim: string, latitude: number, longitude: number, statusBasis = "source_workbook_assumption"): Institution {
  return {
    entity_id: entityId, name, network, entity_type: "institution", status, status_date: "", country: "Belgium", region: "", city: "Brussels",
    source_status_claim: claim, status_basis: statusBasis, latitude, longitude, placed: true, location_precision: "unverified source coordinate",
    aliases: [], programs: ["language"], audiences: ["students"], delivery_modes: [], hosts: [], source_count: 1,
    confidence: { level: "medium", reasons: ["Synthetic end-to-end fixture"], sources: 1, verified_fields: [], conflicts: [] },
    conflicts: [], last_verified: "", last_evidence: "", activity: { items: 0, recent_items: 0 }, updated_at: "",
  };
}

const institutions: Institution[] = [
  institution("ci-1", "Confucius Institute Demo", "team4_confucius_institutes", "active", "Active", 50.85, 4.35),
  institution("ci-renamed", "Confucius Institute Renamed Demo", "team4_confucius_institutes", "renamed", "Active", 51.1, 4.35, "human_verified_registry"),
  institution("luban-1", "Luban Workshop Closed Demo", "team4_luban_workshops", "closed", "Temporarily Closed", 50.9, 4.5),
  institution("luban-2", "Luban Workshop Unknown Demo", "team4_luban_workshops", "unknown", "TBD", 51.0, 4.6),
  institution("as-1", "American Space Active Demo", "team4_american_spaces", "active", "Open", 50.8, 4.7),
  institution("as-2", "American Space Closed Demo", "team4_american_spaces", "closed", "Temporarily Closed", 50.7, 4.8),
  institution("as-relocated", "American Space Relocated Demo", "team4_american_spaces", "relocated", "Open", 51.2, 4.8, "human_verified_registry"),
];

const networks: NetworkRow[] = datasets.slice(0, 3).map((row) => ({ name: row.network, role: row.role, label: row.label, color: row.color, institutions: row.records, placed: row.placed }));
const catalog = {
  catalog_id: "team4", label: "Team 4 network catalog", as_of: "2026-10-29", use_note: "Built-in catalog from supplied team workbooks.", networks: datasets,
  source_inventory: [{ file: "Team 4 workbook.xlsx", sheet: "Directory", rows: 586, notes: "Synthetic fixture" }],
  data_quality_notes: ["Coordinates are retained as unverified source claims."],
  activity_audit: { core_records: 1183, supplementary_records: 108, core_records_with_last_post_date: 0, supplementary_records_with_last_post_date: 0,
    named_site_checks: 5, named_site_checks_with_dated_signals: 3, source_status_claim_counts: { "Luban Workshops": { Active: 36, "Temporarily Closed": 1, TBD: 1 } },
    interpretation: "Workbook labels are not independent proof of current operation." },
  publication_audit: { checked_on: "2026-10-29", rows_searched: 1, matched_page: 1, exact_publication_date_candidate: 1,
    relative_search_age_label: 0, date_shown_in_result: 1, any_date_or_age_signal: 1, no_relevant_result: 0,
    source_scope_counts: { official_or_host: 1 }, result_counts: { dated_or_relative_signal: 1 }, method: "One synthetic row for browser testing.", caveat: "Search evidence does not prove the latest own post.",
    by_network: {}, records: [{ entity_id: "ci-1", name: "Confucius Institute Demo", country: "Belgium", city: "Brussels", network: networks[0].name,
      network_label: networks[0].label, checked_on: "2026-10-29", result: "dated_or_relative_signal", query: "Confucius Institute Demo latest news", fallback_query: "",
      exact_publication_date: "2026-07-03", date_shown_in_result: "3 July 2026", search_age_label: "", date_basis: "date-coded URL", evidence_scope: "official_or_host",
      match_strength: "exact_name", evidence_title: "Demo institute news", evidence_url: "https://example.test/news/2026/07/03/demo",
      candidates: [{ title: "Demo institute news", url: "https://example.test/news/2026/07/03/demo", match: "exact_name", publication_date: "2026-07-03",
        date_basis: "date-coded URL", page_date_candidate: "2026-07-03", search_age_label: "", source_scope: "official_or_host" }] }],
  },
  workbook_status_assumptions: { by_network: Object.fromEntries(datasets.map((row) => [row.label, row.status_counts])), basis: "Source workbook label; human review takes precedence." },
  activity_pulse: [{ network: "Confucius Institutes", checked_on: "2026-10-29", scope: "Network-level", status: "Recent network-level signal", source_url: "https://example.test/ci", signal: "Not a per-site cadence measure." }],
  site_activity_spot_checks: [{ network: "Confucius Institutes", entity_id: "ci-1", entity_name: "Confucius Institute Demo", country: "Belgium", checked_on: "2026-10-29",
    assessment: "A dated public signal exists.", signals: [{ date: "2026-07-03", kind: "official_post", title: "Demo event", note: "Synthetic signal", source_url: "https://example.test/event",
      source_title: "Demo event", source_quality: "official" }] }],
  overlap_claim_counts: { ci_american_spaces: 144, luban_american_spaces_detail_workbook: 38 },
  program_overlap_interpretations: [{ program_type: "Language education", niche_term_ids: "Q1", american_spaces_counterpart: "English teaching", overlap_assessment: "Possible shared program area.",
    team_judgment: "Hypothesis only", strongest_regions: "Multiple", source_origin: { file: "Team workbook.xlsx", sheet: "Overlap", row: 2 } }],
  curated_search_suggestions: [{ id: "s1", label: "Language learning programs", query: '"language learning" "American Spaces" "Confucius Institute"', rationale: "Compare overlapping language programs." }],
} as NetworkCatalog;

const overlap: OverlapResult = {
  rows: [
    { entity_id: "ci-1", name: "Confucius Institute Demo", country: "Belgium", city: "Brussels", nearest_reference: { entity_id: "as-1", name: "American Space Active Demo", city: "Brussels", country: "Belgium", distance_km: 8, band: "25 km", same_city: true }, references_within_km: { "25": 1 }, shared_audiences: ["students"], shared_programs: ["language"] },
    { entity_id: "luban-1", name: "Luban Workshop Closed Demo", country: "Belgium", city: "Brussels", nearest_reference: { entity_id: "as-1", name: "American Space Active Demo", city: "Brussels", country: "Belgium", distance_km: 14, band: "25 km", same_city: true }, references_within_km: { "25": 1 }, shared_audiences: ["students"], shared_programs: ["language"] },
    { entity_id: "luban-2", name: "Luban Workshop Unknown Demo", country: "Belgium", city: "Brussels", nearest_reference: null, references_within_km: {}, shared_audiences: [], shared_programs: [] },
  ],
  by_country: [{ country: "Belgium", subjects: 3, references: 2, subjects_near_reference: 2, shared_audience_pairs: 2 }],
  counts: { subject_institutions: 3, reference_institutions: 2, subjects_not_placed: 0, references_not_placed: 0 },
  method: "Synthetic coordinate comparison for browser testing.", near_km: 25, bands_km: [5, 25, 100, 250],
};

async function mockCatalogApp(page: Page) {
  const state: { imported: string[]; institutionQueries: URLSearchParams[]; networkExports: Array<Record<string, unknown>> } = {
    imported: [], institutionQueries: [], networkExports: [],
  };
  await page.addInitScript((id) => {
    if (!sessionStorage.getItem("sugar.test.initialized")) {
      localStorage.setItem("sugar.workspace", "sugar-workspace://" + id);
      localStorage.setItem("sugar.projectId", id);
      sessionStorage.setItem("sugar.test.initialized", "yes");
    }
    if (!localStorage.getItem("sugar.prefs.v1")) localStorage.setItem("sugar.prefs.v1", JSON.stringify({ onboarded: true, theme: "light", mode: "basic", autoUpdateCheck: false, interpreter: "deterministic" }));
  }, projectId);
  await page.route("https://tiles.openfreemap.org/styles/**", (route) => route.fulfill({ json: { version: 8, glyphs: "https://fonts.example.test/{fontstack}/{range}.pbf", sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#e6edf2" } }] } }));
  await page.route("https://fonts.example.test/**", (route) => route.fulfill({ body: Buffer.alloc(0), contentType: "application/x-protobuf" }));
  await page.route("http://127.0.0.1:8765/api/**", async (route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const body = request.method() === "POST" ? request.postDataJSON() || {} : {};
    const reply = (json: unknown) => route.fulfill({ headers, status: 200, json });
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (path.endsWith("/api/workspaces")) return reply({ workspaces: [{ id: projectId, name: "Team Catalog Test", workspace: "sugar-workspace://" + projectId }] });
    if (path.endsWith("/api/providers")) return reply({ profiles: [], default_profile_id: "", types: [] });
    if (path.endsWith("/api/platforms")) return reply({ platforms: [] });
    if (path.endsWith("/research")) return reply({ summary: { project_id: projectId, name: "Team Catalog Test", research_question: "", status: "ready", run_count: 0 },
      requirement_text: "", plan: null, plan_summary: [], plan_versions: [], settings: {}, members: [], runs: [], notes: [] });
    if (path.endsWith("/research/networks/catalog/import")) {
      state.imported = Array.isArray(body.datasets) ? body.datasets as string[] : [];
      return reply({ selected_datasets: state.imported, selected_records: 1183, added: 1183, updated: 0, skipped_existing: 0, catalog_file: "references/team4_network_catalog.json",
        network_names: networks.map((row) => row.name), note: "Workbook status assumptions are retained." });
    }
    if (path.endsWith("/research/networks/catalog")) return reply(catalog);
    if (path.endsWith("/research/institutions")) {
      state.institutionQueries.push(url.searchParams);
      const selectedStatus = url.searchParams.get("status") || "";
      const rows = state.imported.length ? institutions.filter((row) => !selectedStatus || row.status === selectedStatus) : [];
      return reply({ institutions: rows, total: rows.length, unplaced: 0, facets: { countries: [], programs: [], audiences: [], networks: [] } });
    }
    if (path.endsWith("/research/networks")) return reply({ networks: state.imported.length ? networks : [] });
    if (path.endsWith("/research/overlap")) return reply(overlap);
    if (path.endsWith("/research/map/posts")) return reply({ pins: [], targets: [], flows: [], note: "No posts in fixture", as_of: "2026-10-29", coverage: { unique_posts: 0, mapped_posts: 0, unlocated_posts: 0, undated_posts: 0 } });
    if (path.endsWith("/research/map/institutions/export")) {
      state.networkExports.push(body as Record<string, unknown>);
      return reply({ file: "research/exports/team4-overlap.html", filename: "team4-overlap.html", networks: body.networks || [], counts: {},
        computed_nearby_subject_records: 2, distance_km: body.near_km || 25, country: body.country || "", note: "Synthetic HTML map export." });
    }
    if (path.includes("/files/")) return route.fulfill({ headers, body: "<!doctype html><title>Interactive map</title>", contentType: "text/html" });
    return reply({ events: [], runs: [] });
  });
  return state;
}

const navigate = (page: Page, name: string) => page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name, exact: true }).click();

test("built-in catalog status assumptions, two- and three-network map layers, and HTML export work in the browser", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const state = await mockCatalogApp(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");

  await navigate(page, "Institutions");
  await page.getByRole("button", { name: "Networks & imports", exact: true }).click();
  await page.getByRole("tab", { name: "Built-in team catalog" }).click();
  await expect(page.getByText("Confucius Institutes · Team 4", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("36 active · 1 closed · 1 unknown", { exact: false })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /Confucius Institutes/ })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: /American Spaces/ })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: /CI location leads/ })).not.toBeChecked();

  await page.getByText("Overlap leads, data checks, and activity pulse", { exact: true }).click();
  await expect(page.getByText("Searched 1 catalog rows on 2026-10-29", { exact: false })).toBeVisible();
  await page.getByText("Inspect all 1 row-level search results and export CSV", { exact: true }).click();
  await expect(page.getByText("Exact date candidate:", { exact: false })).toBeVisible();
  await page.getByLabel("Filter publication search results").fill("Confucius Institute Demo");
  await expect(page.getByText("Showing 1–1 of 1 matching rows.", { exact: false })).toBeVisible();
  const auditDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download full audit CSV (1 rows)" }).click();
  expect((await auditDownload).suggestedFilename()).toContain("team4-publication-search-audit");

  await page.getByRole("button", { name: "Add selected datasets to this project" }).click();
  await expect(page.locator(".notice.notice-ok")).toContainText("Added 1,183 records");
  expect(state.imported).toEqual(["confucius_institutes", "luban_workshops", "american_spaces"]);
  await page.getByRole("button", { name: "Close", exact: true }).click();

  await navigate(page, "Map");
  await expect(page.getByRole("note", { name: "Map status legend" })).toContainText("2 active · 2 closed · 1 renamed · 1 relocated · 1 unknown in visible layers");
  await expect(page.getByRole("note", { name: "Map status legend" })).toContainText("workbook labels as an assumption");
  expect(state.institutionQueries.some((params) => params.get("assume_source_status") === "true")).toBe(true);

  await page.getByLabel("Network comparison layers").selectOption("ci_american");
  await expect(page.getByRole("note", { name: "Map status legend" })).toContainText("2 active · 1 closed · 1 renamed · 1 relocated · 0 unknown in visible layers");
  await expect(page.getByRole("button", { name: /Luban Workshops · Team 4/ })).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByRole("button", { name: "Export network map (HTML)" })).toBeEnabled();

  await page.getByRole("button", { name: /^Filters and options/ }).click();
  await page.getByLabel("Distance").selectOption("100");
  const twoLayerDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export network map (HTML)" }).click();
  expect((await twoLayerDownload).suggestedFilename()).toBe("team4-overlap.html");
  expect(state.networkExports.at(-1)).toMatchObject({ networks: ["team4_confucius_institutes", "team4_american_spaces"], near_km: 100, country: "" });

  await page.getByLabel("Network comparison layers").selectOption("all_three");
  await expect(page.getByRole("note", { name: "Map status legend" })).toContainText("2 active · 2 closed · 1 renamed · 1 relocated · 1 unknown in visible layers");
  const threeLayerDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export network map (HTML)" }).click();
  await threeLayerDownload;
  expect(state.networkExports.at(-1)).toMatchObject({ networks: ["team4_confucius_institutes", "team4_luban_workshops", "team4_american_spaces"], near_km: 100 });

  await page.getByRole("radio", { name: "List", exact: true }).click();
  await page.getByRole("row").filter({ hasText: "Luban Workshop Closed Demo" }).click();
  const detail = page.getByRole("complementary", { name: "Selected institution" });
  await expect(detail).toContainText("Temporarily Closed");
  await expect(detail).toContainText("assumption");

  await page.getByRole("row").filter({ hasText: "Confucius Institute Renamed Demo" }).click();
  await expect(detail).toContainText("Renamed");
  await expect(detail).toContainText("human-verified registry status takes precedence");
  await page.getByLabel("Status (Team 4 workbook assumption)").selectOption("renamed");
  await expect(page.getByRole("note", { name: "Map status legend" })).toContainText("0 active · 0 closed · 1 renamed · 0 relocated · 0 unknown in visible layers");
  expect(state.institutionQueries.some((params) => params.get("status") === "renamed" && params.get("assume_source_status") === "true")).toBe(true);

  await page.getByLabel("Status (Team 4 workbook assumption)").selectOption("active");
  await expect(page.getByRole("note", { name: "Map status legend" })).toContainText("2 active · 0 closed · 0 renamed · 0 relocated · 0 unknown in visible layers");
  expect(state.institutionQueries.some((params) => params.get("status") === "active" && params.get("assume_source_status") === "true")).toBe(true);
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
