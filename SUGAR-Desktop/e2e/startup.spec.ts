import { expect, test } from "@playwright/test";

test("desktop provider requests wait for the engine URL and credentials", async ({ page }) => {
  await page.route("**/startup-test", route => route.fulfill({ contentType: "text/html", body: "<html></html>" }));
  const requests: string[] = [];
  await page.route("**/api/providers", async route => {
    requests.push(route.request().url());
    expect(route.request().headers().authorization).toBe("Bearer test-token");
    await route.fulfill({ json: { types: [] } });
  });
  await page.goto("/startup-test");
  await page.evaluate(async () => {
    const w = window as any;
    w.isTauri = true;
    w.__TAURI_INTERNALS__ = { invoke: () => new Promise(resolve => { w.releaseStartup = resolve; }) };
    const bridge = await import(/* @vite-ignore */ "/src/bridge.ts");
    w.providerRequest = bridge.api("/api/providers").then(() => { w.finished = true; });
  });
  await page.waitForTimeout(250);
  expect(requests).toEqual([]);
  await page.evaluate(() => (window as any).releaseStartup({ url: location.origin, token: "test-token" }));
  await expect.poll(() => page.evaluate(() => Boolean((window as any).finished))).toBe(true);
  expect(requests).toHaveLength(1);
});
