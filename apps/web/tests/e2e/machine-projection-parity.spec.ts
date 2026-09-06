import { expect, test } from "@playwright/test";

const COMPONENT_TYPES = [
  "instruction",
  "skill",
  "mcp",
  "hook",
  "command",
  "agent",
  "plugin",
  "setting",
  "cli",
] as const;

test.describe("machine projection parity (REQ-3624, REQ-3626)", () => {
  test("Human/Machine switch keeps catalog query", async ({ page }) => {
    await page.goto("/en/catalog?q=skill&component_type=skill&include_experimental=1");
    const machine = page.locator('[data-ui="projection-machine"]');
    await expect(machine).toHaveAttribute("href", /\/en\/ai\/catalog\?/);
    await expect(machine).toHaveAttribute("href", /q=skill/);
    await expect(machine).toHaveAttribute("href", /component_type=skill/);
    await machine.click();
    await expect(page).toHaveURL(/\/en\/ai\/catalog\?/);
    await expect(page).toHaveURL(/q=skill/);
    await expect(page.locator('[data-ui="machine-page-projection"]')).toBeVisible();
    await expect(page.locator('[data-ui="machine-page-projection"]')).toContainText(
      "component_type: skill",
    );
  });

  test("unknown paths 404 in both projections", async ({ request }) => {
    const human = await request.get("/en/this-route-does-not-exist");
    const machine = await request.get("/en/ai/this-route-does-not-exist");
    expect(human.status()).toBe(404);
    expect(machine.status()).toBe(404);
  });

  test("missing country 404s in both projections", async ({ request }) => {
    const human = await request.get("/en/countries/ZZ");
    const machine = await request.get("/en/ai/countries/ZZ");
    expect(human.status(), "human country").toBe(404);
    expect(machine.status(), "machine country").toBe(404);
  });

  test("missing catalog objects 404 in both projections", async ({ request }) => {
    const invalid = "component_missing";
    const missing = "component_01AAAAAAAAAAAAAAAAAAAAAAAA";
    for (const id of [invalid, missing]) {
      const human = await request.get(`/en/catalog/components/${id}`);
      const machine = await request.get(`/en/ai/catalog/components/${id}`);
      expect(human.status(), `human ${id}`).toBe(404);
      expect(machine.status(), `machine ${id}`).toBe(404);
    }
  });

  test("private publication and invitation pairs share one login redirect", async ({ page }) => {
    for (const route of [
      "/en/publications/plan_missing",
      "/en/ai/publications/plan_missing",
      "/en/invitations/invitation_missing",
      "/en/ai/invitations/invitation_missing",
    ]) {
      const response = await page.goto(route);
      expect(response?.status(), route).toBe(200);
      await expect(page, route).toHaveURL(/\/login/);
    }
  });

  test("every component type keeps an addressable catalog machine pair", async ({ page }) => {
    for (const type of COMPONENT_TYPES) {
      const human = `/en/catalog?component_type=${type}&include_experimental=1`;
      await page.goto(human);
      await expect(page.locator('[data-ui="projection-machine"]')).toHaveAttribute(
        "href",
        new RegExp(`/en/ai/catalog\\?.*component_type=${type}`),
      );
      const response = await page.goto(
        `/en/ai/catalog?component_type=${type}&include_experimental=1`,
      );
      expect(response?.status(), type).toBe(200);
      await expect(page.locator("html")).toHaveAttribute("data-mode", "machine");
      await expect(page.locator('[data-ui="machine-page-projection"]')).toBeVisible();
      await expect(page.locator('[data-ui="machine-page-projection"]')).toContainText(
        `component_type: ${type}`,
      );
    }
  });

  test("services machine document stays paired and query-free switch works", async ({ page }) => {
    const response = await page.goto("/en/ai/services");
    expect(response?.status()).toBe(200);
    await expect(page.locator('[data-ui="machine-page-projection"]')).toBeVisible();
    await expect(page.locator('[data-ui="machine-page-projection"]')).toContainText("](");
    await expect(page.locator('[data-ui="projection-human"]')).toHaveAttribute(
      "href",
      /\/en\/services$/,
    );
  });

  test("machine catalog keeps locale parity", async ({ page }) => {
    for (const locale of ["en", "ru"] as const) {
      const response = await page.goto(`/${locale}/ai/catalog`);
      expect(response?.status(), locale).toBe(200);
      await expect(page.locator("html")).toHaveAttribute("data-mode", "machine");
      await expect(page.locator('[data-ui="human-machine-toggle"]')).toBeVisible();
    }
  });

  test("switch with query works without JavaScript", async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto("/en/catalog?q=hook");
    const machineLink = page.locator('[data-ui="projection-machine"]');
    await expect(machineLink).toHaveAttribute("href", /\/en\/ai\/catalog\?q=hook/);
    await machineLink.click();
    await expect(page).toHaveURL(/\/en\/ai\/catalog\?q=hook/);
    await expect(page.locator("html")).toHaveAttribute("data-mode", "machine");
    await context.close();
  });
});
