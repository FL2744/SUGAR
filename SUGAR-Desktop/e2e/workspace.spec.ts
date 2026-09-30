import { expect, test, type Page, type Route } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const apiOrigin = "http://127.0.0.1:8765";
const corsHeaders = {
  "access-control-allow-origin": "http://127.0.0.1:1420",
  "access-control-allow-methods": "GET, POST, OPTIONS",
  "access-control-allow-headers": "content-type",
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
            ...(savedRequirement ? [{ kind: "research_requirement" }] : []),
            ...(seedEvidence ? [{ kind: "import", path: "data/raw/seed.jsonl", external: false }] : []),
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
            : action === "dataset-browse"
              ? { columns: ["platform", "original_text", "country", "region", "city", "latitude", "longitude"], row_count: 1, matching_rows: 1, rows: [{ platform: "x", original_text: "Public program evidence", country: "Exampleland", region: "North", city: "Harbor", latitude: 12.3, longitude: 45.6 }] }
              : action === "dataset-geography-summary"
                ? { group_by: "hierarchy", total_rows: 1, located_rows: 1, unlocated_rows: 0, groups: [{ label: "Exampleland / North / Harbor", records: 1, share: 1 }], guardrail: "Geographic groups do not establish influence, coordination, or causation." }
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

  await expect(page.getByRole("heading", { name: "Good work starts with a clear question." })).toBeVisible();
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
  await page.getByLabel("Project context notes").fill("Coordinate the review and preserve source context.");
  await page.getByRole("button", { name: "＋ Add member" }).click();
  await page.getByLabel("Member 1 name").fill("Analyst One");
  await page.getByLabel("Member 1 email").fill("analyst@example.test");
  await page.getByLabel("Member 1 role").fill("Lead analyst");
  await page.getByRole("button", { name: "Save project profile" }).click();
  await expect.poll(() => calls.some((call) => call.config?.action === "project-profile-update")).toBe(true);
  expect(calls.find((call) => call.config?.action === "project-profile-update")?.config).toMatchObject({
    notes: "Coordinate the review and preserve source context.",
    members: [{ name: "Analyst One", email: "analyst@example.test", role: "Lead analyst" }],
  });
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
  await page.getByLabel(/Research question/).fill("¿Cómo participan los estudiantes en programas públicos de idiomas en Ciudad Ejemplo?");
  await page.getByLabel("Collection sources").fill("x");
  await page.getByLabel("Translate collected posts").check();
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
  await page.getByRole("button", { name: /Run plan collection/ }).click();
  await expect.poll(() => calls.some((call) => call.operation === "research-collect")).toBe(true);
  expect(calls.find((call) => call.operation === "research-collect")?.config?.translate_posts).toBe(true);

  await page.getByRole("button", { name: "Inspect records" }).click();
  await page.getByRole("button", { name: "Summarize geography" }).click();
  await expect(page.getByRole("region", { name: "Geographic summary" })).toContainText("Exampleland / North / Harbor");
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

test("main browser screens have no automated WCAG 2.2 A/AA violations", async ({ page }) => {
  await mockApi(page, []);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Good work starts with a clear question." })).toBeVisible();
  await expectAccessible(page, "overview");

  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  await navigation.getByRole("button", { name: "Research project" }).click();
  await expectAccessible(page, "research project");
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
});
