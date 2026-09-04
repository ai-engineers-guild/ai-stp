import { mkdir } from "node:fs/promises";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// Same default as scripts/verify-production.mjs: inside this app, under an
// already-ignored directory. VERIFY_REVIEW_DIR overrides both together.
const reviewDir = path.resolve(
  process.cwd(),
  process.env.VERIFY_REVIEW_DIR ?? "test-results/review",
);

test.beforeAll(async () => {
  await mkdir(reviewDir, { recursive: true });
});

test("human and machine shell, shortcuts and contact are operable", async ({ page }) => {
  await page.goto("/en");
  await expect(page.locator('[data-ui="site-footer"]')).toBeVisible();
  const modeToggle = page
    .locator('[data-ui="human-machine-toggle"]')
    .filter({ visible: true })
    .first();
  await expect(modeToggle).toBeVisible();
  const toggleBox = await modeToggle.boundingBox();
  const viewport = page.viewportSize();
  if (!toggleBox || !viewport) throw new Error("projection toggle geometry is unavailable");
  expect(viewport.height - (toggleBox.y + toggleBox.height)).toBeLessThanOrEqual(28);
  expect(toggleBox.y).toBeGreaterThan(viewport.height / 2);

  await modeToggle.locator('[data-ui="projection-machine"]').click();
  await expect(page).toHaveURL(/\/en\/ai(\/)?$/);
  await expect(page.locator("html")).toHaveAttribute("data-mode", "machine");
  await expect(page.locator('[data-ui="machine-site-index"]')).toHaveCount(0);
  await expect(page.locator('[data-ui="landing-workflow-preview"]')).toHaveCount(0);
  await expect(page.locator('[data-ui="machine-page-projection"]')).toBeVisible();
  await expect(page.locator('[data-ui="machine-header"]')).toBeVisible();
  await expect(page.locator('[data-ui="site-header"]')).toHaveCount(0);

  await page.locator('[data-ui="color-theme-toggle"]').filter({ visible: true }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.locator("html")).toHaveAttribute("data-mode", "machine");

  await page.goto("/en/contact");
  await expect(page.locator('[data-ui="contact-form"]')).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);

  await page.goto("/en/login");
  await expect(page).toHaveURL(/\/en\/login/);
  await page.goto("/en/catalog");
  await expect(page).toHaveURL(/\/en\/catalog/);
});

test("contact and profile controls share one accessible size", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/en");

  const contact = page.locator('[data-ui="nav-contact"]');
  const profile = page.locator('[data-ui="nav-account"]');
  await expect(contact).toHaveAttribute("aria-label", "Contact ai_stp (shortcut C)");
  await expect(profile).toHaveAttribute("aria-label", "Sign in");

  const locale = page.locator('[data-ui="locale-select"]');
  const [localeBox, contactBox, profileBox] = await Promise.all([
    locale.boundingBox(),
    contact.boundingBox(),
    profile.boundingBox(),
  ]);
  expect(localeBox).not.toBeNull();
  expect(contactBox).not.toBeNull();
  expect(profileBox).not.toBeNull();
  expect(contactBox?.width).toBe(profileBox?.width);
  expect(contactBox?.height).toBe(profileBox?.height);
  expect(localeBox?.width).toBe(profileBox?.width);
  expect(localeBox?.height).toBe(profileBox?.height);
  expect(contactBox?.width).toBeGreaterThanOrEqual(40);
  expect(contactBox?.height).toBeGreaterThanOrEqual(40);
});

test("documentation root renders content instead of not-found", async ({ page }) => {
  await page.goto("/en/docs");
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
  await expect(page.getByText("Page not found")).toHaveCount(0);
  const nav = page.locator('[data-ui="docs-nav"]');
  await expect(nav.getByRole("link", { name: "For people" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "For agents" })).toBeVisible();
  await nav.getByRole("link", { name: "For agents" }).click();
  await expect(page).toHaveURL(/\/en\/docs\/quickstart\/agent/);
  await expect(page.locator("article.prose-docs > h1").first()).toHaveText("Quickstart for agents");
});

test("machine projection screenshot", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/en/ai");
  await expect(page.locator('[data-ui="machine-page-projection"]')).toBeVisible();
  await page.screenshot({ path: path.join(reviewDir, "machine.png"), fullPage: true });
});

test("projection switch does not insert content or move the document", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/en/catalog");
  const main = page.locator('[data-ui="main-content"]');
  const before = await main.boundingBox();
  if (!before) throw new Error("main geometry is unavailable");

  await page.locator('[data-ui="projection-machine"]').click();
  await expect(page).toHaveURL(/\/en\/ai\/catalog/);
  await expect(page.locator("html")).toHaveAttribute("data-mode", "machine");
  const after = await main.boundingBox();
  if (!after) throw new Error("machine main geometry is unavailable");

  // REQ-3614: top edge of main stays aligned across projections.
  expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(1);
});

test("machine and human catalog texts differ and machine has DOM markdown links", async ({
  page,
}) => {
  await page.goto("/en/catalog");
  const humanText = await page.locator('[data-ui="main-content"]').innerText();

  await page.goto("/en/ai/catalog");
  const machineMain = page.locator('[data-ui="main-content"]');
  const machineText = await machineMain.innerText();
  const machineDom = await machineMain.evaluate((el) => el.textContent || "");

  expect(machineText).not.toBe(humanText);
  // REQ-3605: Markdown link markers are real text nodes, not CSS content.
  expect(machineDom).toContain("](");
});

test("machine document navigation stays on machine URLs", async ({ page }) => {
  await page.goto("/en/ai");
  const catalogLink = page.locator('[data-ui="machine-page-projection"] a[href*="/ai/catalog"]');
  await expect(catalogLink.first()).toBeVisible();
  await catalogLink.first().click();
  await expect(page).toHaveURL(/\/en\/ai\/catalog/);
});

test("every route keeps a machine document and the dock stays pinned", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const routes = [
    "/en/ai",
    "/en/ai/catalog",
    "/en/ai/docs",
    "/en/ai/legal/privacy",
    "/en/ai/contact",
    "/en/ai/login",
    "/en/ai/device-login",
  ];

  for (const route of routes) {
    const response = await page.goto(route);
    expect(response?.status(), route).toBe(200);
    await expect(page.locator("html"), route).toHaveAttribute("data-mode", "machine");
    await expect(page.locator('[data-ui="machine-page-projection"]'), route).toBeVisible();

    const dock = page.locator('[data-ui="human-machine-toggle"]');
    await expect(dock, route).toBeVisible();
    const box = await dock.boundingBox();
    if (!box) throw new Error(`dock geometry is unavailable on ${route}`);
    // Pinned above the fold, not parked at the end of the document.
    expect(Math.round(800 - (box.y + box.height)), route).toBe(24);
  }
});

test("private machine routes render domain documents after sign in", async ({ page }) => {
  await page.goto("/en/login");
  await page
    .getByRole("button", {
      name: /Continue with GitHub|\u0412\u043e\u0439\u0442\u0438 \u0447\u0435\u0440\u0435\u0437 GitHub/i,
    })
    .click();
  await expect(page).toHaveURL(/\/en\/account/);

  const expectations: ReadonlyArray<readonly [string, RegExp]> = [
    ["/en/ai/account", /account_0[0-9A-Z]+/],
    ["/en/ai/devices", /device_0[0-9A-Z]+|No devices/i],
    ["/en/ai/objects", /component_|setup_|Nothing|empty/i],
    ["/en/ai/access", /## /],
    ["/en/ai/reports", /case_|No |empty/i],
  ];

  for (const [route, marker] of expectations) {
    const response = await page.goto(route);
    expect(response?.status(), route).toBe(200);
    await expect(page.locator("html"), route).toHaveAttribute("data-mode", "machine");
    const doc = page.locator('[data-ui="machine-page-projection"]');
    await expect(doc, route).toBeVisible();
    expect(await doc.innerText(), route).toMatch(marker);
  }
});

test("private routes keep one session gate in both projections", async ({ page }) => {
  for (const route of ["/en/account", "/en/ai/account", "/en/devices", "/en/ai/devices"]) {
    const response = await page.goto(route);
    expect(response?.status(), route).toBe(200);
    await expect(page, route).toHaveURL(/\/login/);
  }
});

test("projection dock works without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/en/catalog");
  const machineLink = page.locator('[data-ui="projection-machine"]');
  await expect(machineLink).toHaveAttribute("href", /\/en\/ai\/catalog/);
  await machineLink.click();
  await expect(page).toHaveURL(/\/en\/ai\/catalog/);
  await expect(page.locator("html")).toHaveAttribute("data-mode", "machine");
  await expect(page.locator('[data-ui="projection-machine"]')).toHaveAttribute(
    "aria-current",
    "true",
  );
  await context.close();
});

test("desktop shell screenshot", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/en/contact");
  await page.screenshot({ path: path.join(reviewDir, "desktop.png"), fullPage: true });
});

test("mobile shell screenshot", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/en/contact");
  await page.screenshot({ path: path.join(reviewDir, "mobile.png"), fullPage: true });
});

test("Russian shell fits a narrow mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto("/ru/contact");
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBe(dimensions.clientWidth);
  // Every route keeps the switch, and it must not widen a narrow viewport.
  await expect(page.locator('[data-ui="human-machine-toggle"]')).toBeVisible();
});

test("cookie settings do not float over the mobile layout after consent", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto("/en/catalog");
  await expect(page.locator('[data-ui="human-machine-toggle"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "Cookie settings" })).toHaveCount(0);
});

test("Russian machine chrome is localized", async ({ page }) => {
  await page.goto("/ru/ai");
  await expect(page.locator('[data-ui="machine-header"]')).toBeVisible();
  await expect(page.locator('[data-ui="machine-page-projection"]')).toBeVisible();
  await expect(page.locator('[data-ui="projection-machine"]')).toHaveAttribute(
    "aria-current",
    "true",
  );
});
