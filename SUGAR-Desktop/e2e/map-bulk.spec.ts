import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { PlanSpec, PostMap, PostPin } from "../src/research-types";

const id = "00000000-0000-4000-8000-000000000001";
const headers = { "access-control-allow-origin": "http://127.0.0.1:1420", "access-control-allow-methods": "GET, POST, DELETE, OPTIONS", "access-control-allow-headers": "authorization, content-type" };
const plan = (): PlanSpec => ({
  plan_id: "plan_demo", version: 1, schema_version: "1.0", topic: "education", research_question: "Education programs in Belgium", geography: ["Belgium"], actors: [],
  timeframe: { start: "", end: "", label: "" }, languages: ["auto"], source_scope: "all_enabled", source_categories: [], platforms: [], exclude_platforms: [], search_terms: ["education"],
  queries: [{ id: "q_1", text: "education Belgium", platform: "", language: "", geography: "Belgium", origin: "request", enabled: true, rationale: "Requested topic" }],
  exclusions: [], collection_mode: "discovery", depth: "standard", limits: { query_count: 6, max_posts_per_query: 25, max_pages_per_query: 1, max_items_total: 2000, llm_calls: 500, per_source: {} },
  translation: { policy: "never", target_language: "English", translate_queries: false, max_chars_per_item: 4000, workers: 3 }, dedup: { enabled: true, threshold: .9 }, analysis_goals: [],
  provider: { profile_id: "none", model: "", use_for_planning: false }, refresh: { mode: "manual", interval_hours: 24, watch_queries: [], watch_sources: [], change_detection: true, notify_on_new: false },
  concurrency: { max_workers: 4, per_source_delay_seconds: 1 }, retry: { max_attempts: 3, base_backoff_seconds: 30 }, extraction: { min_chars: 3, fetch_full_text: true, paragraph_split: true },
  interpretation: {}, extra: {}, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
});
const summary = [{ label: "Research topic", value: "education" }, { label: "Region", value: "Belgium" }];

function pins(count = 4): PostPin[] {
  return Array.from({ length: count }, (_, i) => ({
    item_id: `it_${i}`, run_id: "run_demo", author: ["oldest author", "middle author", "newest author", "undated author"][i] || `author ${i}`,
    published_at: ["2026-01-01T12:00:00Z", "2026-01-03T12:00:00Z", "2026-01-04T12:00:00Z", ""][i % 4], platform: "bluesky", url: `https://example.test/${i}`, language: "en",
    original_text: `We welcome education in Belgium. Synthetic example ${i}.`, translated_text: "", origin: { latitude: 50.85 + i % 20 * .01, longitude: 4.35 + i % 20 * .01, kind: "platform coordinates", precision: "exact", label: "Platform coordinates (synthetic)" },
    targets: [{ name: "Belgium", latitude: 50.6, longitude: 4.7, confidence: .8, method: "named in text", precision: "country" }], inferred_location: { name: "Belgium", confidence: .8, method: "named in text" },
    placement: "origin", latitude: 50.85 + i % 20 * .01, longitude: 4.35 + i % 20 * .01, verified: false, verdict: "", verified_by: "", verified_at: "",
    sentiment: { method: "sugar-english-lexicon-v1", basis: "original", status: "scored", reason: "", valence: 1, intensity: .5, direction: -1, matched_terms: ["welcome"] },
  }));
}

async function mockApp(page: Page, options: { saved?: boolean; results?: boolean; count?: number; existing?: boolean } = {}) {
  const state = { plan: options.saved === false ? null : plan(), requirement: "Education programs in Belgium", settings: { rss_feeds: [] as string[], web_seeds: [] as string[] }, saves: [] as PlanSpec[], exports: [] as Record<string, unknown>[], queries: [] as URLSearchParams[] };
  const allPins = pins(options.count);
  const map: PostMap = { pins: allPins, targets: [{ name: "Belgium", posts: allPins.length, last_24h: 1, verified: 0, last_at: "2026-01-04T12:00:00Z", item_ids: allPins.map((p) => p.item_id), platforms: { bluesky: allPins.length }, languages: { en: allPins.length }, cities: {}, latitude: 50.6, longitude: 4.7 }], flows: [], note: "Synthetic test data", as_of: "2026-01-05T00:00:00Z", coverage: { unique_posts: allPins.length + 2, mapped_posts: allPins.length, unlocated_posts: 2, undated_posts: 1 } };
  const run = { run_id: "run_demo", kind: "run", status: "completed", stage: "results", topic: "education", requirement: state.requirement, counts: { collected: allPins.length }, created_at: "2026-01-01T00:00:00Z", started_at: "2026-01-01T00:00:00Z", finished_at: "2026-01-01T01:00:00Z", error_count: 0, warning_count: 0 };
  await page.addInitScript(({ project, existing }) => {
    if (!sessionStorage.getItem("sugar.test.initialized")) {
      if (existing) { localStorage.setItem("sugar.workspace", `sugar-workspace://${project}`); localStorage.setItem("sugar.projectId", project); }
      else { localStorage.removeItem("sugar.workspace"); localStorage.removeItem("sugar.projectId"); }
      sessionStorage.setItem("sugar.test.initialized", "yes");
    }
    if (!localStorage.getItem("sugar.prefs.v1")) localStorage.setItem("sugar.prefs.v1", JSON.stringify({ onboarded: true, theme: "light", mode: "basic", autoUpdateCheck: false, interpreter: "deterministic" }));
  }, { project: id, existing: options.existing !== false });
  await page.route("https://tiles.openfreemap.org/styles/**", (route) => route.fulfill({ json: { version: 8, glyphs: "https://fonts.example.test/{fontstack}/{range}.pbf", sources: {}, layers: [{ id: "background", type: "background", paint: { "background-color": "#e6edf2" } }] } }));
  await page.route("https://fonts.example.test/**", (route) => route.fulfill({ body: Buffer.alloc(0), contentType: "application/x-protobuf" }));
  await page.route("http://127.0.0.1:8765/api/**", async (route) => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname, body = request.method() === "POST" ? request.postDataJSON() || {} : {};
    const reply = (json: unknown) => route.fulfill({ headers, status: 200, json });
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    if (path.endsWith("/api/run")) return reply({ code: 0, events: [{ event: "diagnostics", version: "1.9.0" }], stdout: "", stderr: "" });
    if (path.endsWith("/api/workspaces")) return reply(request.method() === "POST" ? { id, name: "Synthetic research project", workspace: `sugar-workspace://${id}` } : { workspaces: [{ id, name: "Synthetic research project", workspace: `sugar-workspace://${id}` }] });
    if (path.endsWith("/api/providers")) return reply({ profiles: [], default_profile_id: "", types: [] });
    if (path.endsWith("/api/platforms")) return reply({ platforms: ["bluesky", "rss", "web"].map((p) => ({ id: p, label: p, keyword_search: true, state: "ready", description: "", missing: [], requires: [] })) });
    if (path.endsWith("/api/interpret")) return reply({ request: body.text, plan: plan(), summary, method: "deterministic", assumptions: [], issues: [], attempts: [], needs_manual_entry: false, clarifications: [], confidence: 1, provider: {}, defaults: {} });
    if (path.endsWith("/api/plan/normalize")) return reply({ plan: body.plan, summary, issues: [] });
    if (path.endsWith("/research/plan")) { state.plan = body.plan; state.requirement = body.request || state.requirement; state.saves.push(body.plan); return reply({ plan: state.plan, summary, issues: [] }); }
    if (path.endsWith("/research/settings")) { state.settings = { ...state.settings, ...body.changes }; return reply({ settings: state.settings }); }
    if (path.endsWith("/research")) return reply({ summary: { project_id: id, name: "Synthetic research project", research_question: "Education in Belgium", status: "ready", run_count: options.results ? 1 : 0 }, requirement_text: state.requirement, plan: state.plan, plan_summary: summary, plan_versions: [], settings: state.settings, members: [], runs: options.results ? [run] : [], notes: [] });
    if (path.endsWith("/research/institutions")) return reply({ institutions: [], unplaced: 0, facets: { countries: [], programs: [], audiences: [] } });
    if (path.endsWith("/research/networks")) return reply({ networks: [] });
    if (path.endsWith("/research/map/posts")) return reply(map);
    if (path.endsWith("/research/map/export")) { state.exports.push(body); return reply({ archive: "research/exports/map.zip", directory: "research/exports/map", files: ["analysis.csv", "analysis.jsonl", "timeline.csv", "map.geojson", "data-dictionary.json"] }); }
    if (path.endsWith("/runs/run_demo/export")) return reply({ archive: "research/exports/results.zip", directory: "research/exports/results", files: ["items.csv", "items.jsonl"] });
    if (path.endsWith("/runs/run_demo")) return reply({ run });
    if (path.endsWith("/runs/run_demo/results")) {
      state.queries.push(url.searchParams);
      const offset = Number(url.searchParams.get("offset") || 0), limit = Number(url.searchParams.get("limit") || 200);
      const rows = allPins.slice(offset, offset + limit).map((p) => ({ ...p, status: "processed", geography: ["Belgium"], queries: ["education"], is_new: true, known_from_run: "", similarity: 0, query: "education", duplicate_of: "" }));
      return reply({ total: allPins.length, all_items: allPins.length, items: rows, groups: [], group_by: "none", facets: { platforms: [], languages: [], geographies: [], statuses: [] }, duplicates: 0, rejected: 0, excluded: 0 });
    }
    if (path.includes("/files/")) return route.fulfill({ headers, body: "synthetic export", contentType: "application/zip" });
    return reply({ events: [], runs: [] });
  });
  return state;
}

const navigate = (page: Page, name: string) => page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name, exact: true }).click();

async function mockOffice(page: Page) {
  const calls: Array<{ path: string; body: Record<string, any> }> = [];
  const office = { countries: ["Mexico"], institutions: 3, review_needed: 1, activity_labels: { "Active, high confidence": 2, "Status unclear": 1 },
    coding: { proposed: { priority_tier: { A: 2 }, audience_group: { students: 2 } }, confirmed: {}, items_coded: 8 },
    latest_digest: { at: "2026-10-22T10:00:00Z", summary: "One new program; one institution needs review.", institution_changes: [] }, rubric_fingerprint: "test", inbox: "research/capture-inbox" };
  let rubric: Record<string, unknown> = { version: 1, tiers: ["A", "B", "C", "D"].map((tier) => ({ tier, label: tier, terms: [] })), audiences: {}, aliases: {}, alert_terms: [] };
  await page.route("http://127.0.0.1:8765/api/workspaces/*/research/office**", async (route) => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (request.method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    const body = request.method() === "POST" ? request.postDataJSON() || {} : {};
    calls.push({ path, body });
    const reply = (json: unknown) => route.fulfill({ headers, status: 200, json });
    if (path.endsWith("/rubric")) { if (body.rubric) rubric = body.rubric; return reply({ rubric }); }
    if (path.endsWith("/assess")) return reply({ ...office, coded: { proposed: 2 } });
    if (path.endsWith("/feeds")) return reply({ feeds: ["https://news.google.com/rss/search?q=Harbor&hl=es&gl=MX&ceid=MX:es"], warnings: [], note: "Recent entries; coverage varies." });
    if (path.endsWith("/captures")) return reply({ imported: 1, run_id: "run_capture", errors: [] });
    if (path.endsWith("/snapshot") || path.endsWith("/approved-ai")) return reply({ archive: "research/exports/office.zip", directory: "research/exports/office", files: ["country-snapshot.html", "evidence-package.jsonl", "approved-tool-prompt.txt"] });
    return reply(office);
  });
  return calls;
}

test("map grows, expands without overflow, filters dates and animates the same post set", async ({ page }) => {
  const errors: string[] = []; page.on("pageerror", (e) => errors.push(e.message));
  await mockApp(page); await page.setViewportSize({ width: 1440, height: 1000 }); await page.goto("/"); await navigate(page, "Map");
  await expect(page.getByText("of 4 located posts")).toBeVisible();
  const canvas = page.locator(".network-map");
  expect((await canvas.boundingBox())!.height).toBeGreaterThan(650);
  await page.getByRole("button", { name: "Expand map", exact: true }).click();
  const expanded = page.getByRole("dialog", { name: "Expanded research map" });
  await expect(expanded).toBeVisible(); expect((await expanded.boundingBox())!.width).toBeGreaterThan(1370);
  await page.keyboard.press("Escape"); await expect(expanded).toHaveCount(0);
  await page.getByRole("button", { name: /^Posts over time/ }).click();
  await expect(page.getByRole("button", { name: "2026-01-02: 0 posts" })).toBeVisible();
  await page.getByLabel("Through", { exact: true }).fill("2030-01-01");
  await expect(page.getByLabel("Show posts through period")).toHaveValue("3");
  await page.getByLabel("From", { exact: true }).fill("2026-01-03");
  await page.getByLabel("Through", { exact: true }).fill("2026-01-04");
  await expect(page.getByText("of 4 located posts")).toContainText("2");
  await page.getByRole("radio", { name: "List", exact: true }).click();
  await page.getByLabel("Map post publication order").selectOption("oldest");
  const rows = page.getByRole("row").filter({ has: page.getByRole("cell") });
  await expect(rows.first()).toContainText("middle author");
  await page.getByRole("button", { name: "All time", exact: true }).click();
  await page.getByRole("button", { name: "Play over time", exact: true }).click();
  await expect(page.getByLabel("Through", { exact: true })).toHaveValue("2026-01-01");
  await page.getByRole("button", { name: "Pause time", exact: true }).click();
  await page.getByRole("button", { name: "All time", exact: true }).click();
  await page.getByRole("radio", { name: "Map", exact: true }).click();
  await page.getByRole("button", { name: /^Filters and options/ }).click();
  await page.getByLabel("Enable exploratory language axes").check();
  for (const style of ["density", "recency", "intensity", "direction"]) {
    await page.getByLabel("Post map coloring").selectOption(style);
    await expect(page.getByLabel("Post color legend")).toBeVisible();
  }
  await page.getByLabel("Post map coloring").selectOption("valence");
  await expect(page.getByLabel("Post color legend")).toContainText("Negative → positive");
  await page.getByRole("button", { name: /^Filters and options/ }).click();
  await page.getByRole("button", { name: /^Posts over time/ }).click();
  await page.screenshot({ path: "test-results/refined-map.png", fullPage: true });
  const a11y = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(a11y.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }))).toEqual([]);
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("interpreted searches and edited bulk plans survive navigation without running", async ({ page }) => {
  const state = await mockApp(page, { saved: false }); await page.goto("/");
  await page.getByLabel("Research request").fill("Find education programs in Belgium");
  await page.getByRole("button", { name: "Interpret request", exact: true }).click();
  await expect(page.getByText("Search saved to project")).toBeVisible(); expect(state.saves).toHaveLength(1);
  await navigate(page, "Map"); await navigate(page, "Research");
  await expect(page.getByLabel("Research request")).toHaveValue("Find education programs in Belgium");
  await page.getByRole("button", { name: "Edit plan", exact: true }).click();
  await page.getByRole("button", { name: "10,000 items", exact: true }).click();
  await page.getByRole("button", { name: "Save plan", exact: true }).click();
  await expect(page.getByText("Search saved to project")).toBeVisible();
  expect(state.saves.at(-1)?.limits).toMatchObject({ max_items_total: 10000, max_posts_per_query: 10000, max_pages_per_query: 100, target_items: 10000 });
  await navigate(page, "Map"); await navigate(page, "Research");
  await page.getByRole("button", { name: "Edit plan", exact: true }).click();
  await expect(page.getByRole("button", { name: /10,000 items/ })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("button", { name: /^Your own sources/ }).click();
  await page.getByRole("button", { name: "UN news · 6 languages", exact: true }).click();
  await page.getByRole("button", { name: "EU policy and diplomacy", exact: true }).click();
  await page.getByRole("button", { name: "Save sources", exact: true }).click();
  await expect.poll(() => state.settings.rss_feeds.length).toBe(8);
});

test("thousands of posts are paged and map export keeps the active analysis scope", async ({ page }) => {
  const state = await mockApp(page, { results: true, count: 1003 }); await page.goto("/"); await navigate(page, "Results");
  await page.getByLabel("Group by", { exact: true }).selectOption("none");
  await expect(page.getByRole("navigation", { name: "Results pages" })).toContainText("1–200 of 1,003");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Results pages" })).toContainText("201–400 of 1,003");
  await page.getByLabel("Publication order", { exact: true }).selectOption("oldest");
  await expect(page.getByRole("navigation", { name: "Results pages" })).toContainText("1–200 of 1,003");
  expect(state.queries.at(-1)?.get("sort")).toBe("oldest");
  await navigate(page, "Map"); await page.getByRole("button", { name: /^Posts over time/ }).click();
  await page.getByLabel("From", { exact: true }).fill("2026-01-03"); await page.getByLabel("Through", { exact: true }).fill("2026-01-04");
  const download = page.waitForEvent("download"); await page.getByRole("button", { name: "Export mapped posts", exact: true }).click(); await download;
  expect(state.exports[0]).toMatchObject({ since: "2026-01-03", until: "2026-01-04", target: "" });
  await page.setViewportSize({ width: 900, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("a first search creates its project and restores the saved plan after reload", async ({ page }) => {
  const state = await mockApp(page, { saved: false, existing: false }); await page.goto("/");
  await page.getByLabel("Research request").fill("Find education programs in Belgium");
  await page.getByRole("button", { name: "Interpret request", exact: true }).click();
  await expect(page.getByText("Search saved to project")).toBeVisible();
  expect(state.saves).toHaveLength(1);
  await navigate(page, "Map"); await navigate(page, "Research");
  await expect(page.getByRole("region", { name: "Current project plan" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "Current project plan" })).toBeVisible();
  await expect(page.getByLabel("Research request")).toHaveValue("Find education programs in Belgium");
});

test("evidence desk saves a rubric, seeds keyless feeds and imports sanitized capture inputs", async ({ page }) => {
  const state = await mockApp(page); const calls = await mockOffice(page);
  const errors: string[] = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/"); await navigate(page, "Research");
  const desk = page.getByRole("region", { name: "Evidence desk" });
  await expect(desk.getByText("One new program; one institution needs review.")).toBeVisible();
  await desk.getByRole("button", { name: "Refresh local assessments", exact: true }).click();
  await expect(desk.getByRole("status")).toContainText("No model calls");
  await desk.getByRole("button", { name: /^Study rubric and multilingual terminology/ }).click();
  const rules = JSON.parse(await desk.getByLabel("Study rubric JSON").inputValue()); rules.version = 2; rules.aliases = { "Successor Program": ["Programa anterior"] };
  await desk.getByLabel("Study rubric JSON").fill(JSON.stringify(rules));
  await desk.getByRole("button", { name: "Save rubric", exact: true }).click();
  await expect.poll(() => calls.find((c) => c.path.endsWith("/rubric") && c.body.rubric?.version === 2)).toBeTruthy();
  await desk.getByRole("button", { name: /^YouTube and local-language news feeds/ }).click();
  await desk.getByLabel("Institution or news query").fill("Harbor"); await desk.getByLabel("News language").fill("es"); await desk.getByLabel("News country code").fill("MX");
  await desk.getByRole("button", { name: "Preview feed seeds", exact: true }).click(); await desk.getByRole("button", { name: "Save these feeds", exact: true }).click();
  await expect.poll(() => state.settings.rss_feeds.length).toBe(1);
  await desk.getByRole("button", { name: /^Analyst capture inbox/ }).click();
  await desk.getByLabel("Capture original URL").fill("https://example.test/event");
  await desk.getByLabel("Saved HTML captures", { exact: true }).setInputFiles({ name: "event.html", mimeType: "text/html", buffer: Buffer.from("<html><p>Public workshop</p></html>") });
  await expect(desk.getByRole("status")).toContainText("Imported 1 sanitized page");
  expect(calls.find((c) => c.path.endsWith("/captures"))?.body.pages[0].source_url).toBe("https://example.test/event");
  await page.setViewportSize({ width: 900, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/evidence-desk.png", fullPage: true });
  const a11y = await new AxeBuilder({ page }).include(".office-desk").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(a11y.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }))).toEqual([]);
  expect(errors).toEqual([]);
});

test("country snapshots download as standalone HTML and approved AI exports remain analyst initiated", async ({ page }) => {
  await mockApp(page); const calls = await mockOffice(page); await page.goto("/"); await navigate(page, "Research");
  const desk = page.getByRole("region", { name: "Evidence desk" });
  await expect(desk.getByLabel("Snapshot country")).toHaveValue("Mexico");
  expect(calls.some((c) => c.path.endsWith("/approved-ai"))).toBe(false);
  const file = page.waitForEvent("download"); await desk.getByRole("button", { name: "Country snapshot (.html)", exact: true }).click();
  expect((await file).suggestedFilename()).toBe("Mexico-snapshot.html");
  await desk.getByRole("button", { name: "Export for approved AI tool", exact: true }).click();
  await expect(desk.getByRole("button", { name: "Download package (.zip)", exact: true })).toBeVisible();
  expect(calls.filter((c) => c.path.endsWith("/approved-ai"))).toHaveLength(1);
  expect(calls.find((c) => c.path.endsWith("/approved-ai"))?.body.country).toBe("Mexico");
  await desk.getByLabel("Snapshot country").selectOption("");
  await expect(desk.getByRole("button", { name: "Export for approved AI tool", exact: true })).toBeDisabled();
  await expect(desk.getByRole("button", { name: "Download package (.zip)", exact: true })).toHaveCount(0);
});


test("results download saves a run archive and map confidence is included in requests", async ({ page }) => {
  await mockApp(page, { results: true }); await page.goto("/"); await navigate(page, "Results");
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download", exact: true }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toBe("run_demo-results.zip");
  expect(await download.failure()).toBeNull();
  await navigate(page, "Map");
  const request = page.waitForRequest((r) => r.url().includes("/map/posts?") && new URL(r.url()).searchParams.get("min_confidence") === "0.8");
  await page.getByLabel("Minimum post location confidence").selectOption("0.8");
  await request;
});


test("reopening the current project retains results and activity run", async ({ page }) => {
  await mockApp(page, { results: true }); await page.goto("/");
  await navigate(page, "Results");
  await page.getByLabel("Group by", { exact: true }).selectOption("none");
  await expect(page.getByText("We welcome education in Belgium. Synthetic example 0.", { exact: true })).toBeVisible();
  await navigate(page, "Projects");
  await page.getByRole("row", { name: /Synthetic research project/ }).click();
  await navigate(page, "Results");
  await page.getByLabel("Group by", { exact: true }).selectOption("none");
  await expect(page.getByText("We welcome education in Belgium. Synthetic example 0.", { exact: true })).toBeVisible();
  const request = page.waitForRequest((r) => r.url().includes("/runs/run_demo"));
  await navigate(page, "Activity");
  await request;
});

test("project deletion requires confirmation and clears the open project", async ({ page }) => {
  await mockApp(page, { results: true }); await page.goto("/"); await navigate(page, "Projects");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Delete Synthetic research project", exact: true }).click();
  await expect(page.getByRole("button", { name: "Delete Synthetic research project", exact: true })).toBeEnabled();
  page.once("dialog", (dialog) => dialog.accept());
  const deleted = page.waitForRequest((r) => r.method() === "DELETE" && r.url().endsWith(`/workspaces/${id}`));
  await page.getByRole("button", { name: "Delete Synthetic research project", exact: true }).click();
  await deleted;
  await expect.poll(() => page.evaluate(() => localStorage.getItem("sugar.projectId"))).toBeNull();
});
