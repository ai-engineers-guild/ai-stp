import { expect, test } from "@playwright/test";

test.describe("landing → search → detail smoke (REQ-2213)", () => {
  test("bilingual landing and catalog detail path without experimental toggle", async ({
    page,
  }) => {
    await page.goto("/en");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    // Guests must not see Sign out.
    await expect(
      page.getByRole("button", { name: /Sign out|\u0412\u044b\u0439\u0442\u0438/i }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("link", { name: /Sign in|\u0412\u043e\u0439\u0442\u0438/i }).first(),
    ).toBeVisible();

    await page
      .getByRole("link", {
        name: /Browse catalog|\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043a\u0430\u0442\u0430\u043b\u043e\u0433/i,
      })
      .click();
    await expect(page).toHaveURL(/\/en\/catalog/);

    // Experimental remains a catalog default, not a user-facing filter.
    await page.getByRole("button", { name: /^Search|^\u041f\u043e\u0438\u0441\u043a/i }).click();
    const filtersTrigger = page.locator('button[data-ui="catalog-filters"]');
    await filtersTrigger.click();
    await expect(
      page.getByRole("dialog", { name: /Filters|\u0424\u0438\u043b\u044c\u0442\u0440\u044b/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("checkbox", {
        name: /Include experimental|\u044d\u043a\u0441\u043f\u0435\u0440\u0438\u043c\u0435\u043d\u0442\u0430\u043b\u044c\u043d\u044b\u0435/i,
      }),
    ).toHaveCount(0);
    await page
      .getByRole("dialog", { name: /Filters|\u0424\u0438\u043b\u044c\u0442\u0440\u044b/i })
      .getByRole("button", { name: /^(Close|\u0417\u0430\u043a\u0440\u044b\u0442\u044c)$/ })
      .click();

    const firstCard = page.locator("article[data-kind='component']").first();
    await expect(firstCard).toBeVisible({ timeout: 15_000 });
    await firstCard.locator("h3 a").click();
    await expect(page).toHaveURL(/\/en\/catalog\/components\/component_/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("setups use a distinct resource view", async ({ page }) => {
    await page.goto("/en/catalog?resource=setups");
    await expect(
      page.getByRole("heading", { name: /Setups|\u0421\u0435\u0442\u0430\u043f\u044b/i }).first(),
    ).toBeVisible();
    await expect(page.locator("[data-resource='setups']")).toBeVisible();
    await expect(page.locator("article[data-kind='setup']").first()).toBeVisible({
      timeout: 15_000,
    });
  });

  test("three-dots catalog menu does not lock page scroll", async ({ page }) => {
    await page.goto("/en/catalog");
    const firstCard = page.locator("article[data-kind='component']").first();
    await expect(firstCard).toBeVisible({ timeout: 15_000 });
    await firstCard.getByRole("button", { name: "More actions" }).click();
    await expect(page.getByRole("menuitem", { name: "Like" })).toBeVisible();
    const overflow = await page.evaluate(() => getComputedStyle(document.body).overflow);
    expect(overflow).not.toBe("hidden");
  });

  test("collapsed search expands without occupying the initial catalog viewport", async ({
    page,
  }) => {
    await page.goto("/en/catalog");
    const searchTrigger = page.getByRole("button", { name: "Search", exact: true });
    await expect(searchTrigger).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Search" })).toHaveCount(0);
    await searchTrigger.click();
    await expect(page.getByRole("combobox", { name: "Search" })).toBeVisible();
  });

  test("footer stays pinned and Russian policy labels are localized", async ({ page }) => {
    await page.goto("/ru");
    const footer = page.locator('[data-ui="site-footer"]');
    await expect(footer).toBeVisible();
    const footerBottom = await footer.evaluate(
      (element) => element.getBoundingClientRect().bottom + window.scrollY,
    );
    const documentBottom = await page.evaluate(() => document.documentElement.scrollHeight);
    expect(Math.abs(footerBottom - documentBottom)).toBeLessThan(2);
    await expect(
      footer.getByText(
        "\u041a\u043e\u043d\u0444\u0438\u0434\u0435\u043d\u0446\u0438\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u044c",
      ),
    ).toBeVisible();
    await expect(footer.getByText("\u0424\u0430\u0439\u043b\u044b cookie")).toBeVisible();
    await expect(
      footer.getByText(
        "\u041f\u0440\u0430\u0432\u0438\u043b\u0430 \u0441\u0435\u0440\u0432\u0438\u0441\u0430",
      ),
    ).toBeVisible();
    await expect(
      footer.getByText(
        "\u041b\u0438\u0446\u0435\u043d\u0437\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435",
      ),
    ).toBeVisible();
  });
});
