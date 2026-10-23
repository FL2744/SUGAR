import { expect, test, type Page, type Route } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const apiOrigin = "http://127.0.0.1:8765";
const corsHeaders = {
  "access-control-allow-origin": "http://127.0.0.1:1420",
  "access-control-allow-methods": "GET, POST, DELETE, OPTIONS",
  "access-control-allow-headers": "authorization, content-type",
};
type ApiCall = { operation: string; config?: Record<string, unknown> };

async function mockApi(page: Page, calls: ApiCall[], collectionGate?: Promise<void>, seedEvidence = false) {
  await page.route(`${apiOrigin}/api/**`, async (route: Route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }

    if (request.url().endsWith("/api/workspaces") && request.method() === "GET") {
      await route.fulfill({ status: 200, headers: corsHeaders, json: { workspaces: [] } });
      return;
    }
    if (request.url().endsWith("/api/workspaces") && request.method() === "POST") {
      const body = request.postDataJSON() as { name: string };
      const workspace = { id: "project-1", workspace: "sugar-workspace://project-1", name: body.name };
      await route.fulfill({ status: 201, headers: corsHeaders, json: workspace });
      return;
    }
    if (/\/api\/workspaces\/[^/]+\/access(?:\/.*)?$/.test(new URL(request.url()).pathname)) {
      if (request.method() === "POST") {
        calls.push({ operation: "member-access-issue" });
        await route.fulfill({ status: 201, headers: corsHeaders, json: { token: "sugar_member_playwright_once", email: "member@example.test", role: "reviewer", project_id: "project-1", message: "Shown once" } });
      } else if (request.method() === "DELETE") {
        calls.push({ operation: "member-access-revoke" });
        await route.fulfill({ status: 200, headers: corsHeaders, json: { revoked: 1 } });
      } else {
        await route.fulfill({ status: 405, headers: corsHeaders, json: { error: "Method not allowed." } });
      }
      return;
    }
    if (!request.url().endsWith("/api/run") || request.method() !== "POST") {
      await route.fulfill({ status: 404, headers: corsHeaders, json: { error: "Unexpected test API request." } });
      return;
    }

    const body = request.postDataJSON() as { operation: string; config?: Record<string, unknown> };
    calls.push(body);
    let event: Record<string, unknown>;
    if (body.operation === "diagnostics") {
      event = { event: "diagnostics", version: "test-version" };
    } else if (body.operation === "workspace-hub") {
      const action = String(body.config?.action || "");
      const savedRequirement = calls.find((call) => call.operation === "research-requirement")?.config;
      const savedPlan = calls.some((call) => call.operation === "research-plan");
      const data = action === "dashboard"
        ? {
          name: "Browser Test Project", artifact_count: 0, missing_artifacts: 0,
          artifacts: [
            ...(calls.some((call) => call.operation === "search") ? [{ kind: "raw_collection", path: "data/raw/hashtag.csv", external: false }] : []),
            ...(calls.some((call) => call.operation === "research-collect") ? [{ kind: "raw_collection", path: "data/raw/live_collection.csv", external: false }] : []),
            ...(calls.some((call) => call.operation === "ingest") ? [{ kind: "raw_collection", path: "data/raw/public_item_weibo.csv", external: false }] : []),
            ...(seedEvidence ? [{ kind: "import", path: "data/raw/seed.jsonl", external: false }] : []),
            ...(savedRequirement ? [{ kind: "research_requirement" }] : []),
          ],
          research_requirement: savedRequirement ? {
            question: savedRequirement.question, geographies: [], known_entities: [], target_audiences: [],
            languages: ["auto"], excluded_topics: [], preferred_sources: ["x", "bluesky"], timeframe: {},
          } : undefined,
          search_plan: savedPlan ? { branches: [{ branch_id: "branch-1", query: "public programs" }] } : undefined,
          project_profile: { notes: "", members: [], access_control: false },
          research_strategy: calls.some((call) => call.operation === "research-strategy-update")
            ? { review_state: "approved", concepts: [{ concept_id: "concept-1", origin: "interpreted", kind: "activity", value: "public outreach" }] }
            : undefined,
        }
        : action === "project-history"
          ? []
          : action === "project-profile-update"
            ? { notes: body.config?.notes || "", members: body.config?.members || [], access_control: false }
            : action === "project-comment-list"
              ? { comments: calls.filter((call) => call.config?.action === "project-comment-add").map((call, index) => ({ comment_id: `comment-${index}`, actor: "Analyst", body: call.config?.body, created_at: "2026-01-01T00:00:00Z" })) }
              : action === "project-comment-add"
                ? { comment_id: "comment-created", actor: "Analyst", body: body.config?.body, created_at: "2026-01-01T00:00:00Z" }
                : action === "research-template-list"
                  ? { templates: [{ template_id: "public-service-access", name: "Public service access", question: "Where are public services offered?", languages: ["auto"], preferred_sources: ["x"] }] }
                  : action === "research-template-save"
                    ? { template_id: "custom-playwright", name: body.config?.name, question: (body.config?.fields as Record<string, unknown>)?.question }
                    : action === "monitor-list"
                      ? [{ monitor_id: "monitor-1", name: "Weekly listening", status: calls.some((call) => call.config?.action === "monitor-status" && call.config?.status === "paused") ? "paused" : "active", cadence_minutes: 1440, next_due_at: "2026-01-02T00:00:00Z", terms: ["public education"], sources: ["x"] }]
                      : action === "monitor-save"
                        ? { monitor_id: "monitor-1", name: body.config?.name, status: "active", cadence_minutes: body.config?.cadence_minutes, next_due_at: "2026-01-02T00:00:00Z", terms: body.config?.terms, sources: body.config?.sources }
                        : action === "monitor-status"
                          ? { monitor_id: body.config?.monitor_id, name: "Weekly listening", status: body.config?.status, cadence_minutes: 1440 }
                          : action === "monitor-run-due"
                            ? { due_count: 1, run_count: 1, runs: [{ status: "completed" }] }
            : action === "dataset-browse"
              ? { columns: ["platform", "original_text", "country", "region", "city", "latitude", "longitude"], row_count: 1, matching_rows: 1, rows: [{ platform: "x", original_text: "Public program evidence", country: "Exampleland", region: "North", city: "Harbor", latitude: 12.3, longitude: 45.6 }] }
                : action === "dataset-geography-summary"
                ? { group_by: "hierarchy", total_rows: 1, located_rows: 1, unlocated_rows: 0, groups: [{ label: "Exampleland / North / Harbor", records: 1, share: 1 }], guardrail: "Geographic groups do not establish influence, coordination, or causation." }
                : action === "dataset-geography-assign"
                  ? { row_number: body.config?.row_number, provenance: "analyst_manual", region: body.config?.region }
                  : action === "dataset-region-compare"
                    ? { group_by: "hierarchy", left_total: 1, right_total: 1, groups: [{ label: "Exampleland / North / Harbor", left_records: 1, right_records: 1, left_share: 1, right_share: 1, share_difference: 0 }], guardrail: "Descriptive comparison; no causal inference." }
                : undefined;
      if (action === "dataset-export") {
        event = { event: "complete", outputs: [`sugar-workspace://project-1/outputs/exports/example.${String(body.config?.format || "csv")}`] };
      } else {
        event = { event: "workspace_hub_data", action, data: data || { entities: [], count: 0, relationships: 0 } };
      }
    } else if (body.operation === "research-requirement") {
      event = { event: "requirement-created", requirement_id: "rq_browser_test" };
    } else if (body.operation === "research-compile") {
      event = { event: "strategy-review", review_state: "draft", concepts: [{ concept_id: "concept-1", origin: "interpreted", kind: "activity", value: "public outreach" }] };
    } else if (body.operation === "research-strategy-update") {
      event = { event: "strategy-review", review_state: "approved", concepts: [{ concept_id: "concept-1", origin: "interpreted", kind: "activity", value: "public outreach" }] };
    } else if (body.operation === "research-triage") {
      event = { event: "triage-complete", outputs: ["sugar-workspace://project-1/data/observations/triaged.csv"] };
    } else if (body.operation === "research-plan") {
      event = { event: "plan-review", requirement_id: "rq_browser_test", branches: [{ branch_id: "branch-1", query: "public programs" }] };
    } else if (body.operation === "ingest") {
      event = { event: "complete", outputs: ["sugar-workspace://project-1/data/raw/public_item_weibo.csv"] };
    } else if (body.operation === "research-collect") {
      event = { event: "complete", outputs: ["sugar-workspace://project-1/data/raw/live_collection.csv"] };
    } else if (body.operation === "map") {
      event = { event: "complete", outputs: ["sugar-workspace://project-1/outputs/maps/live_map.html"] };
    } else if (body.operation === "search") {
      event = { event: "complete", outputs: ["sugar-workspace://project-1/data/raw/hashtag.csv"] };
    } else {
      event = { event: "complete", outputs: [] };
    }
    if (body.operation === "research-collect" && collectionGate) await collectionGate;
    await route.fulfill({
      status: 200,
      headers: corsHeaders,
      json: { code: 0, events: [event], stdout: "", stderr: "" },
    });
  });
}

async function expectAccessible(page: Page, surface: string) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const violations = results.violations.map(({ id, impact, nodes }) => ({
    id,
    impact,
    targets: nodes.map(({ target, any }) => {
      const contrast = any.find(({ id }) => id === "color-contrast")?.data as
        | { fgColor?: string; bgColor?: string }
        | undefined;
      return [target.join(" "), contrast?.fgColor || "", contrast?.bgColor || ""];
    }),
  }));
  expect(violations, `${surface} accessibility violations`).toEqual([]);
}

test("browser creates a project and saves its research requirement", async ({ page }) => {
  const calls: ApiCall[] = [];
  await mockApi(page, calls);
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Your research, connected." })).toBeVisible();
  await page.getByRole("button", { name: /Create or open project/ }).click();
  const picker = page.getByRole("dialog", { name: "Choose a research project" });
  await expect(picker).toBeVisible();
  await expectAccessible(page, "project picker");
  await picker.getByLabel("New project name").fill("Browser Test Project");
  await picker.getByRole("button", { name: /Create project/ }).click();

  await expect(page.getByRole("heading", { name: "Browser Test Project" })).toBeVisible();
  await page.getByRole("navigation", { name: "Main navigation" })
    .getByRole("button", { name: "Research project" }).click();
  await page.getByLabel(/Research question/).fill("Which public programs are documented?");
  await page.getByLabel("Start date").fill("2025-01-01");
  await page.getByLabel("End date").fill("2025-12-31");
  await page.getByLabel("Languages").fill("es, zh");
  await page.getByRole("tab", { name: /Team & notes/ }).click();
  await page.getByLabel("Project context notes").fill("Coordinate the review and preserve source context.");
  await page.getByRole("button", { name: "＋ Add member" }).click();
  await page.getByLabel("Member 1 name").fill("Analyst One");
  await page.getByLabel("Member 1 email").fill("analyst@example.test");
  await page.getByLabel("Member 1 role").selectOption("analyst");
  await page.getByRole("button", { name: "Save project profile" }).click();
  await expect.poll(() => calls.some((call) => call.config?.action === "project-profile-update")).toBe(true);
  expect(calls.find((call) => call.config?.action === "project-profile-update")?.config).toMatchObject({
    notes: "Coordinate the review and preserve source context.",
    members: [{ name: "Analyst One", email: "analyst@example.test", role: "analyst" }],
  });
  await page.getByRole("tab", { name: /Research brief/ }).click();
  await page.getByLabel("Collection sources").fill("x, bluesky");
  await page.getByLabel("Excluded topics").fill("unrelated tourism");
  await page.getByRole("button", { name: /Save research requirement/ }).click();

  await expect.poll(() => calls.some((call) => call.operation === "research-requirement")).toBe(true);
  const saved = calls.find((call) => call.operation === "research-requirement");
  expect(saved?.config).toMatchObject({
    question: "Which public programs are documented?",
    workspace: "sugar-workspace://project-1",
    since: "2025-01-01",
    until: "2025-12-31",
    languages: ["es", "zh"],
    excluded_topics: ["unrelated tourism"],
    preferred_sources: ["x", "bluesky"],
  });

  await page.getByRole("button", { name: /Build research plan/ }).click();
  await page.getByRole("button", { name: /Run plan collection/ }).click();
  await expect.poll(() => calls.some((call) => call.operation === "research-collect")).toBe(true);
  const collection = calls.find((call) => call.operation === "research-collect");
  expect(collection?.config).toMatchObject({
    sources: ["x", "bluesky"],
    since: "2025-01-01",
    until: "2025-12-31",
    post_languages: ["es", "zh"],
  });
  await page.getByRole("tab", { name: /Evidence/ }).click();
  await expect(page.getByText("1 source records")).toBeVisible();
  await expect(page.getByText("sugar-workspace://project-1/data/raw/live_collection.csv")).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate coded findings" })).toBeVisible();
});

test("known public items become inspectable evidence", async ({ page }) => {
  const calls: ApiCall[] = [];
  await mockApi(page, calls);
  await page.goto("/");
  await page.getByRole("button", { name: /Create or open project/ }).click();
  const picker = page.getByRole("dialog", { name: "Choose a research project" });
  await picker.getByLabel("New project name").fill("Browser Test Project");
  await picker.getByRole("button", { name: /Create project/ }).click();
  await page.getByRole("navigation", { name: "Main navigation" })
    .getByRole("button", { name: "Research project" }).click();
  await page.getByRole("tab", { name: /Evidence/ }).click();
  await page.getByText("Public items & hashtags", { exact: true }).click();
  await page.getByLabel("Public item source").selectOption("weibo");
  await page.getByLabel("Public item URL").fill("https://weibo.com/2/detail/5341549823267451");
  await page.getByRole("button", { name: "Collect public item" }).click();
  await expect.poll(() => calls.some((call) => call.operation === "ingest")).toBe(true);
  expect(calls.find((call) => call.operation === "ingest")?.config).toMatchObject({
    source: "weibo", identifier: "https://weibo.com/2/detail/5341549823267451",
  });
  await expect(page.getByText("1 source records")).toBeVisible();
  await expect(page.getByRole("button", { name: "Prepare human review" })).toBeVisible();
  await page.getByLabel("Mastodon public hashtag").fill("#education");
  await page.getByRole("button", { name: "Collect hashtag" }).click();
  await expect.poll(() => calls.some((call) => call.operation === "search")).toBe(true);
  expect(calls.find((call) => call.operation === "search")?.config).toMatchObject({
    sources: ["mastodon"], terms: ["#education"],
  });
  await expect(page.getByText("1 source records")).toBeVisible();
  await expect(page.getByText("sugar-workspace://project-1/data/raw/hashtag.csv")).toBeVisible();
});

test("active collection accepts scope edits, source retries, and cooperative stop requests", async ({ page }) => {
  const calls: ApiCall[] = [];
  let releaseCollection!: () => void;
  const collectionGate = new Promise<void>((resolve) => { releaseCollection = resolve; });
  await mockApi(page, calls, collectionGate);
  await page.goto("/");
  await page.getByRole("button", { name: /Create or open project/ }).click();
  const picker = page.getByRole("dialog", { name: "Choose a research project" });
  await picker.getByLabel("New project name").fill("Live Control Project");
  await picker.getByRole("button", { name: /Create project/ }).click();
  await page.getByRole("navigation", { name: "Main navigation" })
    .getByRole("button", { name: "Research project" }).click();
  await page.getByLabel(/Research question/).fill("Which public programs are documented?");
  await page.getByLabel("Collection sources").fill("x, bluesky");
  await page.getByRole("button", { name: /Save research requirement/ }).click();
  await expect.poll(() => calls.some((call) => call.operation === "research-requirement")).toBe(true);
  await page.getByRole("button", { name: /Build research plan/ }).click();
  await expect(page.getByRole("button", { name: /Run plan collection/ })).toBeVisible();
  await page.getByRole("button", { name: /Run plan collection/ }).click();
  await expect(page.getByRole("heading", { name: "Live collection controls" })).toBeVisible();
  await expect.poll(() => calls.some((call) => call.operation === "research-collect")).toBe(true);

  await page.getByLabel("Live search queries").fill("public programs\neducation exchange");
  await page.getByLabel("Live collection sources").fill("bluesky, mastodon");
  await page.getByLabel("Live excluded topics").fill("tourism");
  await page.getByLabel("Live post languages").fill("es, zh");
  await page.getByLabel("Live start date").fill("2025-01-01");
  await page.getByLabel("Live end date").fill("2025-12-31");
  await page.getByRole("button", { name: "Apply changes" }).click();
  await expect.poll(() => calls.some((call) => call.operation === "research-collect-control" && !call.config?.start)).toBe(true);
  const update = calls.find((call) => call.operation === "research-collect-control" && !call.config?.start);
  expect(update?.config).toMatchObject({
    sources: ["bluesky", "mastodon"], terms: ["public programs", "education exchange"],
    excluded_topics: ["tourism"], post_languages: ["es", "zh"], since: "2025-01-01", until: "2025-12-31",
  });

  await page.getByLabel("Source to retry").selectOption("mastodon");
  await page.getByRole("button", { name: "Retry source" }).click();
  await expect.poll(() => calls.some((call) => call.config?.retry_source === "mastodon")).toBe(true);
  await page.getByRole("button", { name: "Stop after current request" }).click();
  await expect.poll(() => calls.some((call) => call.operation === "research-collect-control" && call.config?.cancel === true)).toBe(true);
  expect(calls.find((call) => call.operation === "research-collect")?.config).not.toHaveProperty("start");
  releaseCollection();
  await expect(page.getByRole("heading", { name: "Live collection controls" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Run plan collection/ })).toBeEnabled();
});

test("research text remains comfortably readable without page overflow", async ({ page }) => {
  await mockApi(page, []);
  await page.setViewportSize({ width: 1280, height: 820 });
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" })
    .getByRole("button", { name: "Research project" }).click();

  const fontSizes = await page.locator(
    ".page-content :is(p, small, .eyebrow, .field-block > span, button, input, textarea, select)",
  ).evaluateAll((elements) => elements
    .filter((element) => (element as HTMLElement).offsetParent !== null)
    .map((element) => Number.parseFloat(getComputedStyle(element).fontSize)));
  expect(fontSizes.length).toBeGreaterThan(10);
  expect(Math.min(...fontSizes)).toBeGreaterThanOrEqual(16);

  await page.setViewportSize({ width: 390, height: 844 });
  const pageOverflowsHorizontally = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(pageOverflowsHorizontally).toBe(false);
});

test("AI interpretation, translation, geographic summary, coded findings, and export are wired to the backend", async ({ page }) => {
  const calls: ApiCall[] = [];
  await mockApi(page, calls, undefined, true);
  await page.goto("/");
  await page.getByRole("button", { name: /Create or open project/ }).click();
  const picker = page.getByRole("dialog", { name: "Choose a research project" });
  await picker.getByLabel("New project name").fill("Complete Workflow Project");
  await picker.getByRole("button", { name: /Create project/ }).click();

  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Research project" }).click();
  await page.getByRole("tab", { name: /Team & notes/ }).click();
  await page.getByRole("textbox", { name: "Project comment" }).fill("Check the scope before the scheduled run.");
  await page.getByRole("button", { name: "Add comment" }).click();
  await expect(page.getByRole("log", { name: "Project comments" })).toContainText("Check the scope before the scheduled run.");

  await page.getByRole("button", { name: "Add member" }).click();
  await page.getByLabel("Member 1 name").fill("Project reviewer");
  await page.getByLabel("Member 1 email").fill("member@example.test");
  await page.getByLabel("Member 1 role").selectOption("reviewer");
  await page.getByRole("button", { name: "Save project profile" }).click();
  await page.getByRole("button", { name: "Issue access" }).click();
  await expect(page.getByLabel("One-time member access token")).toHaveValue("sugar_member_playwright_once");
  await page.getByRole("button", { name: "Revoke access" }).click();
  await expect(page.getByLabel("One-time member access token")).toHaveCount(0);
  expect(calls.some((call) => call.operation === "member-access-issue")).toBe(true);
  expect(calls.some((call) => call.operation === "member-access-revoke")).toBe(true);

  await page.getByRole("tab", { name: /Monitoring/ }).click();
  await page.getByLabel("Listening post name").fill("Weekly listening");
  await page.getByLabel("Listening post search terms").fill("public education programs");
  await page.getByRole("button", { name: "Save listening post" }).click();
  await expect(page.locator(".monitor-list")).toContainText("Weekly listening");
  await page.getByRole("button", { name: "Run due checks now" }).click();
  expect(calls.some((call) => call.config?.action === "monitor-run-due")).toBe(true);
  await page.getByRole("button", { name: "Pause" }).click();
  expect(calls.some((call) => call.config?.action === "monitor-status" && call.config?.status === "paused")).toBe(true);

  await page.getByRole("tab", { name: /Research brief/ }).click();
  await page.getByRole("button", { name: "Load templates" }).click();
  await page.getByLabel("Research requirement template").selectOption("public-service-access");
  await page.getByRole("button", { name: "Use template" }).click();
  await page.getByLabel(/Research question/).fill("¿Cómo participan los estudiantes en programas públicos de idiomas en Ciudad Ejemplo?");
  await page.getByLabel("Collection sources").fill("x");
  await page.getByLabel("Translate collected posts").check();
  await page.getByLabel("Infer broad locations for mapping").check();
  await page.getByLabel("New research template name").fill("Spanish education scan");
  await page.getByRole("button", { name: "Save template" }).click();
  expect(calls.some((call) => call.config?.action === "research-template-save")).toBe(true);
  await page.getByRole("button", { name: /Save research requirement/ }).click();
  await expect.poll(() => calls.some((call) => call.operation === "research-requirement")).toBe(true);

  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByLabel("LLM provider key").fill("test-openai-key");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Research project" }).click();
  await page.getByRole("button", { name: "Interpret with AI" }).click();
  await expect(page.getByText("AI interpretation · draft")).toBeVisible();
  await page.getByRole("button", { name: "Approve interpretation" }).click();
  await expect(page.getByText("AI interpretation · approved")).toBeVisible();
  await page.getByRole("button", { name: "Build research plan" }).click();
  await expect.poll(() => calls.some((call) => call.operation === "research-plan")).toBe(true);
  await page.getByText("Per-platform collection limits").click();
  await page.getByLabel("X maximum posts per query").fill("3");
  await page.getByRole("button", { name: /Run plan collection/ }).click();
  await expect.poll(() => calls.some((call) => call.operation === "research-collect")).toBe(true);
  expect(calls.find((call) => call.operation === "research-collect")?.config?.translate_posts).toBe(true);
  expect(calls.find((call) => call.operation === "research-collect")?.config?.infer_locations).toBe(true);
  expect(calls.find((call) => call.operation === "research-collect")?.config?.platform_tuning).toEqual({ x: { max_posts_per_query: 3 } });

  await page.getByRole("tab", { name: /Evidence/ }).click();
  await page.getByRole("button", { name: "Inspect records" }).click();
  await page.getByRole("button", { name: "Summarize geography" }).click();
  await expect(page.getByRole("region", { name: "Geographic summary" })).toContainText("Exampleland / North / Harbor");
  await page.getByRole("button", { name: "Create evidence map" }).click();
  await expect.poll(() => calls.some((call) => call.operation === "map")).toBe(true);
  await expect(page.getByText("Interactive evidence map ready")).toBeVisible();
  await page.getByText("Geographic review & comparison", { exact: true }).click();
  await page.getByLabel("Assigned region").fill("Central");
  await page.getByLabel("Geography assignment note").fill("Confirmed against the source listing");
  await page.getByRole("button", { name: "Save analyst assignment" }).click();
  await expect.poll(() => calls.some((call) => call.config?.action === "dataset-geography-assign" && call.config?.region === "Central")).toBe(true);
  await page.getByLabel("Comparison dataset path").fill("sugar-file://project-1/data/raw/seed.jsonl");
  await page.getByRole("button", { name: "Compare regions" }).click();
  await expect.poll(() => calls.some((call) => call.config?.action === "dataset-region-compare")).toBe(true);
  await expect(page.getByRole("columnheader", { name: "Baseline" })).toBeVisible();
  await page.getByLabel("Evidence export format").selectOption("geojson");
  await page.getByRole("button", { name: "Export data" }).click();
  await expect.poll(() => calls.some((call) => call.config?.action === "dataset-export" && call.config?.format === "geojson")).toBe(true);

  await page.getByRole("button", { name: "Generate coded findings" }).click();
  await expect(page.getByRole("heading", { name: "AI-coded findings" })).toBeVisible();
  expect(calls.some((call) => call.operation === "research-triage")).toBe(true);
});

test("provider credentials remain session-only in the browser", async ({ page }) => {
  await mockApi(page, []);
  await page.goto("/");
  await page.getByRole("button", { name: "Settings" }).click();
  const secret = "playwright-session-secret";
  const keyField = page.getByLabel("LLM provider key");
  await keyField.fill(secret);

  const savedValues = await page.evaluate(() => JSON.stringify(Object.values(localStorage)));
  expect(savedValues).not.toContain(secret);
  await page.reload();
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByLabel("LLM provider key")).toHaveValue("");
});

test("opening a saved project restores its question and switching projects clears drafts and previews", async ({ page }) => {
  const calls: ApiCall[] = [];
  await mockApi(page, calls);
  const first = { id: "saved-project", workspace: "sugar-workspace://saved-project", name: "Saved project" };
  const second = { id: "empty-project", workspace: "sugar-workspace://empty-project", name: "Empty project" };
  await page.addInitScript((workspace) => localStorage.setItem("sugar.workspace", workspace), first.workspace);
  await page.route(`${apiOrigin}/api/workspaces`, (route) => route.fulfill({ status: 200, headers: corsHeaders, json: { workspaces: [first, second] } }));
  await page.route(`${apiOrigin}/api/run`, async (route) => {
    const body = route.request().postDataJSON() as ApiCall;
    if (body.config?.action !== "dashboard") { await route.fallback(); return; }
    calls.push(body);
    const saved = body.config.workspace === first.workspace;
    const data = saved ? {
      name: first.name, artifacts: [{ kind: "import", path: "data/raw/saved.jsonl" }],
      research_requirement: { question: "Saved project question", geographies: ["Exampleland"] },
      project_profile: { notes: "Saved project notes", members: [{ name: "Reviewer", email: "reviewer@example.test", role: "reviewer" }] },
    } : { name: second.name, artifacts: [], project_profile: { notes: "", members: [] } };
    await route.fulfill({ status: 200, headers: corsHeaders, json: { code: 0, events: [{ event: "workspace_hub_data", action: "dashboard", data }], stdout: "", stderr: "" } });
  });
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Research project" }).click();
  await expect(page.getByLabel(/Research question/)).toHaveValue("Saved project question");
  await page.getByRole("tab", { name: /Team & notes/ }).click();
  await expect(page.getByLabel("Project context notes")).toHaveValue("Saved project notes");
  await page.getByRole("tab", { name: /Evidence/ }).click();
  await page.getByRole("button", { name: "Inspect records" }).click();
  await expect(page.getByRole("cell", { name: "Public program evidence", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: /Research brief/ }).click();
  await page.getByLabel(/Research question/).fill("Unsaved draft from the previous project");
  await page.getByRole("button", { name: "Change project" }).click();
  await page.getByRole("dialog").getByRole("button", { name: /Empty project/ }).click();
  await expect(page.getByRole("heading", { name: "Empty project", exact: true })).toBeVisible();
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Research project" }).click();
  await expect(page.getByLabel(/Research question/)).toHaveValue("");
  await page.getByRole("tab", { name: /Team & notes/ }).click();
  await expect(page.getByLabel("Project context notes")).toHaveValue("");
  await expect(page.getByLabel("Member 1 name")).toHaveCount(0);
  await page.getByRole("tab", { name: /Evidence/ }).click();
  await expect(page.getByRole("cell", { name: "Public program evidence", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Inspect records" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Change project" })).toBeEnabled();
});

test("a newly created project loads its saved dashboard while creation is finishing", async ({ page }) => {
  const calls: ApiCall[] = [];
  await mockApi(page, calls, undefined, true);
  let releaseDashboard!: () => void;
  let markDashboardRequested!: () => void;
  const dashboardGate = new Promise<void>((resolve) => { releaseDashboard = resolve; });
  const dashboardRequested = new Promise<void>((resolve) => { markDashboardRequested = resolve; });
  await page.route(`${apiOrigin}/api/run`, async (route) => {
    const body = route.request().postDataJSON() as ApiCall;
    if (body.config?.action === "dashboard") {
      markDashboardRequested();
      await dashboardGate;
    }
    await route.fallback();
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Create or open project/ }).click();
  await page.getByRole("dialog").getByRole("button", { name: /Create project/ }).click();
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Research project" }).click();
  await dashboardRequested;
  try {
    await expect(page.getByRole("button", { name: "Change project" })).toBeDisabled();
  } finally { releaseDashboard(); }
  await page.getByRole("tab", { name: /Evidence/ }).click();
  await expect(page.getByRole("button", { name: "Inspect records" })).toBeEnabled();
  expect(calls.some((call) => call.config?.action === "dashboard")).toBe(true);
});

test("institution pagination exposes records beyond 300 and filters can be cleared", async ({ page }) => {
  await mockApi(page, []);
  await page.addInitScript(() => localStorage.setItem("sugar.workspace", "sugar-workspace://project-1"));
  const entities = Array.from({ length: 305 }, (_, index) => ({
    entity_id: `institution-${index + 1}`, name: `Institution ${index + 1}`,
    network: "Example network", entity_type: "institution", status: "unknown",
  }));
  await page.route(`${apiOrigin}/api/run`, async (route) => {
    const body = route.request().postDataJSON() as ApiCall;
    if (body.config?.action !== "registry-list") { await route.fallback(); return; }
    await route.fulfill({ status: 200, headers: corsHeaders, json: { code: 0, events: [{ event: "workspace_hub_data", action: "registry-list", data: { entities, count: entities.length } }], stdout: "", stderr: "" } });
  });
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Institutions & map" }).click();
  const pagination = page.getByRole("navigation", { name: "Institution pages" });
  await expect(pagination).toContainText("Page 1 of 4");
  await expect(page.locator(".registry-row")).toHaveCount(100);
  await expect(pagination.getByRole("button", { name: "Previous" })).toBeDisabled();
  for (let index = 0; index < 3; index += 1) await pagination.getByRole("button", { name: "Next" }).click();
  await expect(page.locator(".registry-row")).toHaveCount(5);
  await expect(page.locator(".registry-list")).toContainText("Institution 305");
  await expect(pagination.getByRole("button", { name: "Next" })).toBeDisabled();
  await page.getByLabel("Search institutions").fill("Institution 305");
  await expect(page.locator(".registry-row")).toHaveCount(1);
  await expect(pagination).toHaveCount(0);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(pagination).toContainText("Page 1 of 4");
  await expect(page.locator(".registry-row")).toHaveCount(100);
});

test("main browser screens have no automated WCAG 2.2 A/AA violations", async ({ page }) => {
  test.setTimeout(60_000);
  await mockApi(page, []);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your research, connected." })).toBeVisible();
  await expectAccessible(page, "overview");

  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  await navigation.getByRole("button", { name: "Research project" }).click();
  await expectAccessible(page, "research project");
  for (const section of ["Evidence", "Team & notes", "Monitoring"]) {
    await page.getByRole("tab", { name: new RegExp(section) }).click();
    await expectAccessible(page, section);
  }
  await navigation.getByRole("button", { name: "Institutions & map" }).click();
  await expectAccessible(page, "institutions and map");
  await navigation.getByRole("button", { name: "Run history" }).click();
  await expectAccessible(page, "run history");
  await page.getByRole("button", { name: "Settings" }).click();
  await expectAccessible(page, "settings");
  await page.getByLabel("Color theme").selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expectAccessible(page, "dark settings");
  await navigation.getByRole("button", { name: "Overview" }).click();
  await expectAccessible(page, "dark overview");
  await navigation.getByRole("button", { name: "Research project" }).click();
  await expectAccessible(page, "dark research project");
  for (const section of ["Research brief", "Evidence", "Team & notes"]) {
    await page.getByRole("tab", { name: new RegExp(section) }).click();
    await expectAccessible(page, `dark ${section}`);
  }
});

test("quick actions and project tabs support keyboard navigation", async ({ page }) => {
  await mockApi(page, []);
  await page.goto("/");
  const opener = page.getByRole("button", { name: "Open quick actions" });
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "Quick actions" });
  const input = dialog.getByRole("combobox", { name: "Search actions" });
  await expect(input).toBeFocused();
  await input.fill("zzzzzz");
  await expect(dialog.getByText("No matching actions")).toBeVisible();
  await input.fill("evidence");
  await expect(dialog.getByRole("option")).toHaveCount(1);
  await expectAccessible(page, "quick actions");
  await input.press("Enter");
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("tab", { name: /Evidence/ })).toHaveAttribute("aria-selected", "true");
  const evidenceTab = page.getByRole("tab", { name: /Evidence/ });
  await evidenceTab.focus();
  await evidenceTab.press("ArrowRight");
  await expect(page.getByRole("tab", { name: /Team & notes/ })).toBeFocused();
  await expect(page.getByRole("tabpanel", { name: /Team & notes/ })).toBeVisible();
  await page.getByRole("tab", { name: /Team & notes/ }).press("Home");
  await expect(page.getByRole("tab", { name: /Research brief/ })).toBeFocused();
  await page.keyboard.press("Control+k");
  await expect(dialog).toBeVisible();
  await input.press("Escape");
  await expect(dialog).not.toBeVisible();
});

test("mobile navigation keeps every screen and project section reachable", async ({ page }, testInfo) => {
  await mockApi(page, []);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await page.screenshot({ path: testInfo.outputPath("overview-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  for (const screen of ["Research project", "Institutions & map", "Run history", "Settings", "Overview"]) {
    await navigation.getByRole("button", { name: screen, exact: true }).click();
    await expect(navigation.getByRole("button", { name: screen, exact: true })).toBeVisible();
    expect(await page.locator(".page-content").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  }
  await navigation.getByRole("button", { name: "Research project", exact: true }).click();
  for (const section of ["Evidence", "Team & notes", "Monitoring", "Research brief"]) {
    await page.getByRole("tab", { name: new RegExp(section) }).click();
    await expect(page.getByRole("tabpanel", { name: new RegExp(section) })).toBeVisible();
    expect(await page.locator(".page-content").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  }
  await page.screenshot({ path: testInfo.outputPath("research-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await navigation.getByRole("button", { name: "Overview", exact: true }).click();
  await page.screenshot({ path: testInfo.outputPath("overview-dark-mobile.png"), fullPage: true });
});

test("institution list view and source inspector preserve keyboard focus and reject malformed links", async ({ page }) => {
  await mockApi(page, []);
  await page.addInitScript(() => localStorage.setItem("sugar.workspace", "sugar-workspace://project-1"));
  await page.route(`${apiOrigin}/api/run`, async (route) => {
    const body = route.request().postDataJSON() as ApiCall;
    if (body.config?.action !== "registry-list") { await route.fallback(); return; }
    const data = { entities: [{ entity_id: "test-1", name: "Example Education Center", city: "Harbor", country: "Exampleland", status: "active", network: "Public education", public_links: ["https://", "javascript:alert(1)", "https://example.org/source"] }], count: 1 };
    await route.fulfill({ status: 200, headers: corsHeaders, json: { code: 0, events: [{ event: "workspace_hub_data", action: "registry-list", data }], stdout: "", stderr: "" } });
  });
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Institutions & map" }).click();
  await page.getByRole("button", { name: "List view", exact: true }).click();
  await expect(page.locator(".map-column")).not.toBeVisible();
  const row = page.locator(".registry-row");
  await row.click();
  const inspector = page.getByRole("dialog", { name: "Example Education Center" });
  await expect(inspector).toBeVisible();
  await expect(inspector.getByRole("link")).toHaveCount(1);
  await expect(inspector.getByRole("link")).toHaveAttribute("href", "https://example.org/source");
  await expect(inspector.getByRole("button", { name: "Close inspector" })).toBeFocused();
  await expectAccessible(page, "source inspector");
  await page.keyboard.press("Escape");
  await expect(inspector).not.toBeVisible();
  await expect(row).toBeFocused();
  await page.getByRole("button", { name: "Map view", exact: true }).click();
  await expect(page.locator(".map-column")).toBeVisible();
});

test("run history can be searched and filtered to issues", async ({ page }) => {
  await mockApi(page, []);
  await page.addInitScript(() => localStorage.setItem("sugar.workspace", "sugar-workspace://project-1"));
  await page.route(`${apiOrigin}/api/run`, async (route) => {
    const body = route.request().postDataJSON() as ApiCall;
    if (body.config?.action !== "project-history") { await route.fallback(); return; }
    const data = [{ command: "evidence-import", status: "completed" }, { command: "collection-failed", status: "failed" }];
    await route.fulfill({ status: 200, headers: corsHeaders, json: { code: 0, events: [{ event: "workspace_hub_data", action: "project-history", data }], stdout: "", stderr: "" } });
  });
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Run history" }).click();
  await expect(page.locator(".history-panel .activity-row")).toHaveCount(2);
  await page.getByLabel("Search run history").fill("import");
  await expect(page.locator(".history-panel .activity-row")).toHaveCount(1);
  await page.getByRole("button", { name: "Issues only" }).click();
  await expect(page.getByRole("heading", { name: "No matching activity" })).toBeVisible();
  await page.getByLabel("Search run history").fill("");
  await expect(page.locator(".history-panel .activity-row")).toHaveCount(1);
  await expect(page.locator(".history-panel .activity-row")).toContainText("Collection Failed");
});
