import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

type MockOptions = { configured?: boolean; checkError?: string; downloadError?: string; installError?: string; current?: boolean; automaticChecks?: boolean; automaticDownloads?: boolean; lastChecked?: string; holdDownload?: boolean; theme?: "light" | "dark" };

async function mockDesktop(page: Page, options: MockOptions = {}) {
  const headers = { "access-control-allow-origin": "http://127.0.0.1:1420", "access-control-allow-methods": "GET, POST, DELETE, OPTIONS", "access-control-allow-headers": "authorization, content-type" };
  await page.route("http://127.0.0.1:8765/api/**", async (route) => {
    if (route.request().method() === "OPTIONS") return route.fulfill({ headers, status: 204 });
    const path = new URL(route.request().url()).pathname;
    const json = path.endsWith("/api/run") ? { code: 0, events: [{ event: "diagnostics", version: "1.9.0" }], stdout: "", stderr: "" }
      : path.endsWith("/api/providers") ? { profiles: [], default_profile_id: "", types: [], credential_storage: "local" }
      : path.endsWith("/api/platforms") ? { platforms: [] } : { workspaces: [], events: [], runs: [] };
    return route.fulfill({ headers, json });
  });
  await page.addInitScript((options) => {
    const state = { ...options, calls: [] as string[], finishDownload: null as (() => void) | null };
    Object.assign(window, { isTauri: true, __updateTest: state });
    localStorage.removeItem("sugar.workspace"); localStorage.removeItem("sugar.projectId");
    localStorage.setItem("sugar.prefs.v1", JSON.stringify({ onboarded: true, theme: options.theme || "light", mode: "basic", autoUpdateCheck: false, updateChannel: "stable", interpreter: "deterministic" }));
    if (options.automaticChecks !== undefined) localStorage.setItem("sugar.updates.automaticChecks", String(options.automaticChecks));
    if (options.automaticDownloads !== undefined) localStorage.setItem("sugar.updates.automaticDownloads", String(options.automaticDownloads));
    if (options.lastChecked) localStorage.setItem("sugar.updates.lastCheck.1.6.1", options.lastChecked);
    let callback = 0;
    Object.assign(window, { __TAURI_INTERNALS__: {
      transformCallback: () => ++callback,
      unregisterCallback: () => {},
      invoke: async (command: string, args: Record<string, unknown>) => {
        state.calls.push(command);
        if (command === "start_local_api") return { url: "http://127.0.0.1:8765", token: "local-test-token" };
        if (command === "updater_status") return { configured: state.configured !== false, currentVersion: "1.6.1" };
        if (command === "check_for_update") {
          if (state.checkError) throw state.checkError;
          return state.current ? null : { version: "1.7.0", currentVersion: "1.6.1", notes: "Faster research exports.\n<script>untrusted release text</script>" };
        }
        if (command === "download_update") {
          const channel = args.onProgress as { onmessage: (data: { downloaded: number; total: number | null }) => void };
          channel.onmessage({ downloaded: 25_000_000, total: 100_000_000 });
          if (state.holdDownload) await new Promise<void>((resolve) => { state.finishDownload = resolve; });
          if (state.downloadError) throw state.downloadError;
          channel.onmessage({ downloaded: 100_000_000, total: 100_000_000 });
          return;
        }
        if (command === "install_update") {
          if (state.installError) throw state.installError;
          return new Promise(() => {}); // A real host exits/restarts here.
        }
        if (command === "run_backend") return { code: 0, events: [{ event: "diagnostics", version: "1.6.1" }], stdout: "", stderr: "" };
        throw new Error(`Unexpected native command: ${command}`);
      },
    } });
  }, options);
}

async function settings(page: Page) {
  await page.getByRole("button", { name: "Settings", exact: true }).last().click();
  await page.getByRole("navigation", { name: "Settings sections" }).getByRole("button", { name: "Updates", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Software updates" })).toBeVisible();
}

async function updateCalls(page: Page, command: string) {
  return page.evaluate((command) => {
    const state = (window as unknown as { __updateTest: { calls: string[] } }).__updateTest;
    return state.calls.filter((call) => call === command).length;
  }, command);
}

async function changeMock(page: Page, changes: MockOptions) {
  await page.evaluate((changes) => Object.assign((window as unknown as { __updateTest: MockOptions }).__updateTest, changes), changes);
}

test("desktop automatically checks, shows download progress, and restarts only after confirmation", async ({ page }, testInfo) => {
  await mockDesktop(page, { holdDownload: true });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "View update" })).toBeVisible();
  expect(await updateCalls(page, "check_for_update")).toBe(1);
  expect(await updateCalls(page, "download_update")).toBe(0);
  await page.getByRole("button", { name: "View update" }).click();
  await page.getByText("What’s new in 1.7.0").click();
  await expect(page.locator(".update-release-notes p")).toContainText("<script>untrusted release text</script>");
  await page.getByRole("button", { name: "Download update", exact: true }).click();
  await expect(page.getByRole("progressbar", { name: "Update download progress" })).toHaveAttribute("value", "25000000");
  await expect(page.getByRole("button", { name: "Check for updates", exact: true })).toBeDisabled();
  await page.evaluate(() => (window as unknown as { __updateTest: { finishDownload: () => void } }).__updateTest.finishDownload());
  await expect(page.getByRole("button", { name: "Install and restart", exact: true })).toBeVisible();
  expect(await updateCalls(page, "install_update")).toBe(0);
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(accessibility.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("updates-ready-desktop.png"), fullPage: true });
  await page.getByRole("button", { name: "Install and restart", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Ready to restart SUGAR?" });
  await expect(dialog.getByRole("button", { name: "Keep working" })).toBeFocused();
  await dialog.getByRole("button", { name: "Keep working" }).click();
  expect(await updateCalls(page, "install_update")).toBe(0);
  await page.getByRole("button", { name: "Install and restart", exact: true }).click();
  await dialog.getByRole("button", { name: "Install and restart now" }).click();
  await expect(page.getByText("Installing update. SUGAR will restart…")).toBeVisible();
  expect(await updateCalls(page, "install_update")).toBe(1);
  await expect(page.getByRole("button", { name: "New project", exact: true }).last()).toBeDisabled();
});

test("automatic downloads verify in the background without installing", async ({ page }) => {
  await mockDesktop(page, { automaticDownloads: true });
  await page.goto("/");
  await settings(page);
  await expect(page.getByRole("button", { name: "Install and restart", exact: true })).toBeVisible();
  expect(await updateCalls(page, "download_update")).toBe(1);
  expect(await updateCalls(page, "install_update")).toBe(0);
  await page.getByLabel("Check for updates automatically").uncheck();
  await expect(page.getByLabel("Download updates automatically")).toBeDisabled();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("sugar.updates.automaticChecks"))).toBe("false");
  await page.getByRole("button", { name: "Dismiss update notice" }).click();
  await expect(page.locator(".update-notice")).not.toBeVisible();
  await expect(page.getByText("SUGAR 1.7.0 is ready to install", { exact: true })).toBeVisible();
});

test("failed checks recover on retry and failed signatures never offer installation", async ({ page }) => {
  await mockDesktop(page, { automaticChecks: false, checkError: "Network is offline" });
  await page.goto("/");
  await settings(page);
  const check = page.getByRole("button", { name: "Check for updates", exact: true });
  await check.click();
  await expect(page.locator(".update-error")).toContainText("Network is offline");
  await expect(check).toBeEnabled();
  await changeMock(page, { checkError: "", downloadError: "Signature verification failed" });
  await check.click();
  await page.getByRole("button", { name: "Download update", exact: true }).click();
  await expect(page.locator(".update-error")).toContainText("Signature verification failed");
  await expect(page.getByRole("button", { name: "Install and restart", exact: true })).toHaveCount(0);
  await changeMock(page, { downloadError: "", installError: "Installer could not start" });
  await page.getByRole("button", { name: "Download update", exact: true }).click();
  await page.getByRole("button", { name: "Install and restart", exact: true }).click();
  await page.getByRole("button", { name: "Install and restart now" }).click();
  await expect(page.locator(".update-error")).toContainText("Installer could not start");
  await expect(page.getByRole("button", { name: "Install and restart", exact: true })).toBeEnabled();
  expect(await updateCalls(page, "download_update")).toBe(2);
});

test("automatic checks respect their cooldown but manual checks still run", async ({ page }) => {
  await mockDesktop(page, { lastChecked: new Date().toISOString(), current: true });
  await page.goto("/");
  await settings(page);
  await page.waitForTimeout(2800);
  expect(await updateCalls(page, "check_for_update")).toBe(0);
  await page.getByRole("button", { name: "Check for updates", exact: true }).click();
  await expect(page.getByText("You’re up to date", { exact: true })).toBeVisible();
  expect(await updateCalls(page, "check_for_update")).toBe(1);
  await expect(page.getByLabel("Download updates automatically")).not.toBeChecked();
});

test("unsigned development builds explain manual updating without polling", async ({ page }) => {
  await mockDesktop(page, { configured: false });
  await page.goto("/");
  await settings(page);
  await expect(page.getByText("Automatic updates aren’t enabled in this build.")).toBeVisible();
  await expect(page.getByRole("link", { name: /View release downloads/ })).toHaveAttribute("href", "https://github.com/FL2744/SUGAR/releases/latest");
  await expect(page.getByRole("button", { name: "Check for updates", exact: true })).toHaveCount(0);
  expect(await updateCalls(page, "check_for_update")).toBe(0);
});

test("update controls fit mobile and remain readable in dark mode", async ({ page }, testInfo) => {
  await mockDesktop(page, { automaticChecks: false, theme: "dark" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await settings(page);
  await page.getByRole("button", { name: "Check for updates", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(await page.locator(".page-content").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("updates-mobile-dark.png"), fullPage: true });
});
