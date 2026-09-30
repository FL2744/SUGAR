import { expect, test, type Page, type Route } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const apiOrigin = "http://127.0.0.1:8765";
const corsHeaders = {
  "access-control-allow-origin": "http://127.0.0.1:1420",
  "access-control-allow-methods": "GET, POST, OPTIONS",
  "access-control-allow-headers": "content-type",
};

async function mockApi(page: Page, calls: Array<Record<string, unknown>>) {
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
      const data = action === "dashboard"
        ? { name: "Browser Test Project", artifact_count: 0, missing_artifacts: 0, artifacts: [] }
        : action === "project-history"
          ? []
          : { entities: [], count: 0, relationships: 0 };
      event = { event: "workspace_hub_data", action, data };
    } else if (body.operation === "research-requirement") {
      event = { event: "requirement-created", requirement_id: "rq_browser_test" };
    } else if (body.operation === "research-plan") {
      event = { event: "plan-review", requirement_id: "rq_browser_test", branches: [] };
    } else {
      event = { event: "complete", outputs: [] };
    }
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
  const calls: Array<Record<string, unknown>> = [];
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
