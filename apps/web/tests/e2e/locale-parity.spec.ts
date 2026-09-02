import { expect, test } from "@playwright/test";

/**
 * REQ-2203 / REQ-2311: equivalent scenarios on /ru; locale switch keeps the route.
 */
test.describe("locale parity (REQ-2203, REQ-2311)", () => {
  test("Russian landing and catalog detail path mirrors English smoke", async ({ page }) => {
    await page.goto("/ru");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.locator('[data-ui="site-footer"]')).toContainText(
      "\u0420\u0435\u0435\u0441\u0442\u0440 \u0418\u0418-\u0441\u0435\u0442\u0430\u043f\u043e\u0432",
    );

    await page
      .getByRole("link", {
        name: /Browse catalog|\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043a\u0430\u0442\u0430\u043b\u043e\u0433/i,
      })
      .click();
    await expect(page).toHaveURL(/\/ru\/catalog/);

    await page.goto("/ru/catalog?resource=components");
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

  test("landing hero video follows the active locale", async ({ page }) => {
    await page.goto("/ru");
    const preview = page.locator('[data-ui="landing-workflow-preview"]');
    await expect(preview.locator("source").first()).toHaveAttribute(
      "src",
      "/brand/hero-preview.webm",
    );
    await page.locator("#locale-select").click();
    await expect(page).toHaveURL(/\/en\/?$/);
    await expect(preview.locator("source").first()).toHaveAttribute(
      "src",
      "/brand/hero-preview-en.webm",
    );
    await page.locator("#locale-select").click();
    await expect(page).toHaveURL(/\/ru\/?$/);
    await expect(preview.locator("source").first()).toHaveAttribute(
      "src",
      "/brand/hero-preview.webm",
    );
  });

  test("Russian login + devices smoke", async ({ page }) => {
    await page.goto("/ru/login");
    await page
      .getByRole("button", {
        name: /Continue with GitHub|\u0412\u043e\u0439\u0442\u0438 \u0447\u0435\u0440\u0435\u0437 GitHub/i,
      })
      .click();
    await expect(page).toHaveURL(/\/ru\/account/);
    await expect(page.getByText(/account_01JQZK7B8N4M6P2R9T5V0X3Y7Z/)).toBeVisible();

    await page.goto("/ru/devices");
    await expect(page.getByRole("heading", { name: "fixture-device" })).toBeVisible();
  });
});
