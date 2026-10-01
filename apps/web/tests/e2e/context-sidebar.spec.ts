import path from "node:path";
import { mkdir } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const corporate = process.env["AI_STP_CORPORATE_E2E"] === "offline";

test.describe("shared sidebar behavior", () => {
  test.skip(!corporate, "Corporate session and capabilities require the Corporate build");
  test("anonymous navigation has no desktop rail or mobile trigger", async ({ page }) => {
    for (const width of [360, 768, 1440]) {
      await page.setViewportSize({ width, height: 800 });
      await page.goto("/en/corporate/overview");
      await expect(page).toHaveURL(/\/corporate\/login/);
      await expect(page.locator('[data-ui="context-sidebar"]')).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Open menu", exact: true })).toHaveCount(0);
      await expect(
        page.locator('[data-ui="site-header"]').getByRole("link", { name: "ai_stp", exact: true }),
      ).toBeVisible();
    }
  });
  test("direct administration entry includes the authorized rail in its first HTML", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const errors: string[] = [];
    page.on("pageerror", (error) => {
      console.error(error.stack);
      errors.push(error.message);
    });
    page.on("console", (message) => {
      if (
        message.type() === "error" &&
        /hydration|did not match|chunkloaderror|loading chunk|cannot read properties|runtime error/i.test(
          message.text(),
        )
      )
        errors.push(message.text());
    });
    page.on("requestfailed", (request) => {
      if (new URL(request.url()).pathname.startsWith("/_next/static/chunks/")) {
        errors.push(`${request.url()} ${request.failure()?.errorText ?? "request failed"}`);
      }
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/en/login?returnTo=%2Fen%2Fcorporate%2Foverview");
    await page.getByRole("button", { name: /Continue with GitHub/i }).click();
    await page.waitForURL("**/en/corporate/overview");

    const response = await page.goto("/en/corporate/organization/admins/access");
    expect(response?.status()).toBe(200);
    expect(await response?.text()).toContain('data-ui="context-sidebar"');

    const sidebar = page.locator('[data-ui="context-sidebar"]');
    await expect(sidebar.getByRole("heading", { name: "Administration" })).toBeVisible();
    await expect(sidebar.getByText("Back to Overview", { exact: true })).toHaveCount(0);
    await expect(sidebar.getByRole("button", { name: /People & Access/ })).toBeVisible();

    const localizedResponse = await page.goto("/ru/corporate/organization/admins/access");
    expect(localizedResponse?.status()).toBe(200);
    expect(await localizedResponse?.text()).toContain('data-ui="context-sidebar"');
    const localizedSidebar = page.locator('[data-ui="context-sidebar"]');
    await expect(
      localizedSidebar.getByRole("heading", { name: "Администрирование" }),
    ).toBeVisible();
    await expect(localizedSidebar.locator('a[href$="/corporate/overview"]')).toHaveCount(0);
    expect(errors).toEqual([]);
  });
  test("preserves sections, root-only collapse, flyout keyboard access and responsive modal", async ({
    page,
  }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/en/login?returnTo=%2Fen%2Fcorporate%2Foverview");
    await page.getByRole("button", { name: /Continue with GitHub/i }).click();
    await page.waitForURL("**/en/corporate/overview");
    const sidebar = page.locator('[data-ui="context-sidebar"]');
    await expect(sidebar.getByRole("link", { name: "Catalog", exact: true })).toBeVisible();
    const catalog = sidebar.locator('a[href$="/corporate/catalog"]');
    await catalog.click();
    await expect(page).toHaveURL(/\/corporate\/catalog/);
    await expect(sidebar.getByRole("link", { name: "Overview", exact: true })).toBeVisible();
    await sidebar.getByRole("link", { name: "Overview", exact: true }).click();
    await expect(page).toHaveURL(/\/corporate\/overview$/);
    await expect(
      page.getByRole("heading", { name: "Corporate engineering", exact: true }),
    ).toBeVisible();
    await expect(sidebar.getByRole("link", { name: "Catalog", exact: true })).toBeVisible();
    await page
      .locator('[data-ui="site-header"]')
      .getByRole("button", { name: "Collapse navigation", exact: true })
      .click();
    await expect(sidebar).toHaveAttribute("data-collapsed", "true");
    await expect(sidebar.locator('[data-ui="corporate-nav-employees"]')).toHaveCount(0);
    const organization = sidebar.getByRole("button", { name: "Organization", exact: true });
    await organization.focus();
    await page.keyboard.press("Enter");
    const menu = page.getByRole("menu", { name: "Organization", exact: true });
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: "Teams", exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(organization).toBeFocused();
    const dir = path.resolve(process.cwd(), "../../.impeccable/review");
    await mkdir(dir, { recursive: true });
    await page.screenshot({ path: path.join(dir, `sidebar-root-only-${info.project.name}.png`) });
    await page.reload();
    await expect(sidebar).toHaveAttribute("data-collapsed", "true");
    for (const width of [360, 768, 1023]) {
      await page.setViewportSize({ width, height: 800 });
      const trigger = page.getByRole("button", { name: "Open menu", exact: true });
      await trigger.click();
      const dialog = page.getByRole("dialog", { name: "Primary navigation", exact: true });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByRole("link", { name: "Catalog", exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      expect(
        (await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations,
      ).toEqual([]);
      await page.keyboard.press("Escape");
      await expect(trigger).toBeFocused();
    }
    await page.getByRole("button", { name: "Open menu", exact: true }).click();
    await page.setViewportSize({ width: 1024, height: 700 });
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(sidebar).toBeVisible();
    await expect(sidebar).toHaveAttribute("data-collapsed", "true");
    await page.setViewportSize({ width: 390, height: 800 });
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Open menu", exact: true }).click();
    await page.getByRole("dialog").getByRole("link", { name: "Catalog", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.goBack();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.goForward();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.locator('[data-ui="site-header"] [data-ui="nav-account"]').click();
    await page.getByRole("menuitem", { name: /Sign out/i }).click();
    await expect(sidebar).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Open menu", exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});

test("Storybook sidebar scenarios render and support keyboard interaction", async ({
  page,
}, info) => {
  test.setTimeout(180_000);
  const url = process.env["AI_STP_STORYBOOK_URL"];
  test.skip(!url, "Opt in with AI_STP_STORYBOOK_URL pointing at the built Storybook");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const base = `${url}/iframe.html?id=ui-kit-layouts-contextsidebar--`;
  page.on("requestfailed", (request) => {
    console.error(`Storybook asset failed: ${request.url()} ${request.failure()?.errorText}`);
  });
  for (const story of [
    "overview",
    "organization-detail",
    "collapsed",
    "administration",
    "administration-collapsed",
    "dark",
    "short-desktop",
    "long-labels",
    "restricted",
    "denied-administration",
  ]) {
    await page.setViewportSize({
      width: story === "short-desktop" ? 1024 : 1440,
      height: story === "short-desktop" ? 420 : 900,
    });
    await page.goto(`${base}${story}&viewMode=story`);
    const rail = page.locator('[data-ui="context-sidebar"]');
    await expect(rail, `Storybook scenario ${story}`).toBeVisible({ timeout: 15_000 });
    if (story === "dark") {
      await expect(page.locator("html")).toHaveClass(/dark/);
      await expect(rail.getByRole("button", { name: "Expand Security", exact: true })).toHaveCSS(
        "color",
        await rail.evaluate((node) => getComputedStyle(node).color),
      );
    }
    await expect(rail).toHaveAttribute("data-collapsed", String(story.includes("collapsed")));
    if (story === "denied-administration") {
      await expect(rail.getByRole("link", { name: "Overview", exact: true })).toBeVisible();
      await expect(rail.getByRole("link", { name: "Catalog", exact: true })).toBeVisible();
      await expect(rail.locator('[aria-current="page"]')).toHaveCount(0);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect(
      (await new AxeBuilder({ page }).include('[data-ui="context-sidebar"]').analyze()).violations,
    ).toEqual([]);
    if (story === "collapsed") {
      const organization = rail.getByRole("button", { name: "Organization", exact: true });
      await organization.focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("menuitem", { name: "Teams", exact: true })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(organization).toBeFocused();
    }
  }
  for (const story of ["signed-out", "loading-or-unavailable", "no-organization-access"]) {
    await page.goto(`${base}${story}&viewMode=story`);
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.locator('[data-ui="context-sidebar"]')).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Open menu", exact: true })).toHaveCount(0);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${base}administration&viewMode=story`);
  const desktopRail = page.locator('[data-ui="context-sidebar"]');
  await page.getByRole("button", { name: "Collapse navigation", exact: true }).click();
  await expect(desktopRail).toHaveAttribute("data-collapsed", "true");
  await page.getByRole("button", { name: "Expand navigation", exact: true }).click();
  await expect(desktopRail).toHaveAttribute("data-collapsed", "false");
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto(`${base}mobile&viewMode=story`);
  await page.getByRole("button", { name: "Open menu", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  const dir = path.resolve(process.cwd(), "../../.impeccable/review");
  await mkdir(dir, { recursive: true });
  await page.screenshot({
    path: path.join(dir, `sidebar-storybook-mobile-${info.project.name}.png`),
  });
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual(
    [],
  );
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Open menu", exact: true })).toBeFocused();
  await page.goto(`${base}denied-administration-mobile&viewMode=story`);
  await page.getByRole("button", { name: "Open menu", exact: true }).click();
  const deniedDialog = page.getByRole("dialog");
  await expect(deniedDialog.getByRole("link", { name: "Overview", exact: true })).toBeVisible();
  await expect(deniedDialog.getByRole("link", { name: "Catalog", exact: true })).toBeVisible();
  await expect(deniedDialog.locator('[aria-current="page"]')).toHaveCount(0);
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual(
    [],
  );
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Open menu", exact: true })).toBeFocused();
  expect(errors).toEqual([]);
});
