import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

test("shared navigation keeps personal routes in the header and preserves the full footer", async ({
  page,
}, info) => {
  test.setTimeout(180_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 900 });
  const response = await page.goto("/en/login");
  expect(response?.status()).toBe(200);
  const sidebar = page.locator('[data-ui="context-sidebar"]');
  const corporate = page.url().includes("/corporate/");
  if (corporate) await expect(sidebar).toHaveCount(0);
  else await expect(sidebar).toBeVisible();
  await expect(
    sidebar.locator(
      'a[href*="/account"], [data-ui="nav-account-group"], [data-ui="nav-objects"], [data-ui="nav-access"], [data-ui="nav-reports"], [data-ui="nav-devices"]',
    ),
  ).toHaveCount(0);
  if (!corporate) expect(await sidebar.innerText()).not.toMatch(/corporate/i);
  await expect(page.locator('[data-ui="site-header"] [data-ui="nav-account"]')).toBeVisible();
  const footer = page.locator('[data-ui="site-footer"]');
  await footer.scrollIntoViewIfNeeded();
  await expect(
    footer.getByText("The AI setup registry, not just a skill catalog.", { exact: true }),
  ).toBeVisible();
  await expect(footer.getByRole("heading", { name: "Product", exact: true })).toBeVisible();
  expect((await footer.boundingBox())?.height).toBeGreaterThan(200);
  const profile = (await footer.getByRole("heading", { name: "Company", exact: true }).count())
    ? "saas"
    : "corporate";
  await page.locator('[data-ui="color-theme-toggle"]').click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  const review = path.resolve(process.cwd(), "../../.impeccable/review");
  await mkdir(review, { recursive: true });
  await page.screenshot({
    path: path.join(review, `shell-recovery-${profile}-${info.project.name}-desktop.png`),
  });
  await page.setViewportSize({ width: 390, height: 800 });
  if (corporate) {
    await expect(page.getByRole("button", { name: "Open menu", exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
    return;
  }
  await page.getByRole("button", { name: "Open menu", exact: true }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toBeVisible();
  await expect(drawer.locator('a[href*="/account"], [data-ui="nav-account-group"]')).toHaveCount(0);
  expect(await drawer.innerText()).not.toMatch(/corporate/i);
  await page.screenshot({
    path: path.join(review, `shell-recovery-${profile}-${info.project.name}-mobile.png`),
  });
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  expect(errors).toEqual([]);
});

test("concurrent localized routes remain renderable after navigation", async ({ request }) => {
  test.setTimeout(240_000);
  const routes = [
    "/en/login",
    "/ru/login",
    "/en/docs",
    "/ru/docs",
    "/en/corporate/organization/admins",
    "/ru/corporate/employees/new",
  ];
  for (let round = 0; round < 2; round++) {
    const responses = await Promise.all(
      routes.map((route) => request.get(route, { timeout: 120_000 })),
    );
    for (const [index, response] of responses.entries()) {
      expect(response.status(), routes[index]).toBeLessThan(500);
      expect(await response.text(), routes[index]).not.toContain(
        "Unexpected non-whitespace character after JSON",
      );
    }
  }
});

test("human and machine shells do not expose a selectable context", async ({ page }) => {
  for (const path of ["/en/catalog", "/en/ai/catalog"]) {
    await page.goto(path);
    await expect(page.locator('[data-ui="product-context-switcher"]')).toHaveCount(0);
    await expect(page.locator('[data-ui="product-context-navigation"]')).toHaveCount(0);
    await expect(page.getByText("Context unavailable", { exact: true })).toHaveCount(0);
  }
});
