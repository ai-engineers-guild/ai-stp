import { expect, test } from "@playwright/test";

test.describe("landing → search → detail smoke (REQ-2213)", () => {
  test("bilingual landing and catalog detail path without experimental toggle", async ({
    page,
  }) => {
    await page.goto("/en");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    // Guests must not see Sign out.
    await expect(page.getByRole("button", { name: /Sign out|Выйти/i })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /Sign in|Войти/i }).first()).toBeVisible();

    await page.getByRole("link", { name: /Browse catalog|Открыть каталог/i }).click();
    await expect(page).toHaveURL(/\/en\/catalog/);

    // Experimental remains a catalog default, not a user-facing filter.
    await page.getByRole("button", { name: /^Search|^Поиск/i }).click();
    const filtersTrigger = page.locator('button[data-ui="catalog-filters"]');
    await filtersTrigger.click();
    await expect(page.getByRole("dialog", { name: /Filters|Фильтры/i })).toBeVisible();
    await expect(
      page.getByRole("checkbox", { name: /Include experimental|экспериментальные/i }),
    ).toHaveCount(0);
    await page
      .getByRole("dialog", { name: /Filters|Фильтры/i })
      .getByRole("button", { name: /^(Close|Закрыть)$/ })
      .click();

    const firstCard = page.locator("article[data-kind='component']").first();
    await expect(firstCard).toBeVisible({ timeout: 15_000 });
    await firstCard.locator("h3 a").click();
    await expect(page).toHaveURL(/\/en\/catalog\/components\/component_/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("setups use a distinct resource view", async ({ page }) => {
    await page.goto("/en/catalog?resource=setups");
    await expect(page.getByRole("heading", { name: /Setups|Сетапы/i }).first()).toBeVisible();
    await expect(page.locator("[data-resource='setups']")).toBeVisible();
    await expect(page.locator("article[data-kind='setup']").first()).toBeVisible({
      timeout: 15_000,
    });
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
    await expect(footer.getByText("Конфиденциальность")).toBeVisible();
    await expect(footer.getByText("Файлы cookie")).toBeVisible();
    await expect(footer.getByText("Правила сервиса")).toBeVisible();
    await expect(footer.getByText("Лицензирование")).toBeVisible();
  });
});
