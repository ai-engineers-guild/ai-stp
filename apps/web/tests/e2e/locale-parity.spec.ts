import { expect, test } from "@playwright/test";

/**
 * REQ-2203 / REQ-2311: equivalent scenarios on /ru; locale switch keeps the route.
 */
test.describe("locale parity (REQ-2203, REQ-2311)", () => {
  test("Russian landing and catalog detail path mirrors English smoke", async ({ page }) => {
    await page.goto("/ru");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.locator('[data-ui="site-footer"]')).toContainText("Реестр ИИ-сетапов");

    await page.getByRole("link", { name: /Browse catalog|Открыть каталог/i }).click();
    await expect(page).toHaveURL(/\/ru\/catalog/);

    const card = page.getByRole("link", {
      name: /fixture-component|firstparty-security-skill|pytest-guard-skill/i,
    });
    await expect(card.first()).toBeVisible({ timeout: 15_000 });
    await card.first().click();
    await expect(page).toHaveURL(/\/ru\/catalog\/components\/component_/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("locale switcher preserves the current route", async ({ page }) => {
    await page.goto("/en/catalog");
    await expect(page).toHaveURL(/\/en\/catalog/);
    await page.locator("#locale-select").click();
    await expect(page).toHaveURL(/\/ru\/catalog/);
    await page.locator("#locale-select").click();
    await expect(page).toHaveURL(/\/en\/catalog/);
  });

  test("Russian login + devices smoke", async ({ page }) => {
    await page.goto("/ru/login");
    await page.getByRole("button", { name: /Continue with GitHub|Войти через GitHub/i }).click();
    await expect(page).toHaveURL(/\/ru\/account/);
    await expect(page.getByText(/account_01JQZK7B8N4M6P2R9T5V0X3Y7Z/)).toBeVisible();

    await page.goto("/ru/devices");
    await expect(page.getByRole("heading", { name: "fixture-device" })).toBeVisible();
  });
});
