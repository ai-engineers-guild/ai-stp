import { expect, test } from "@playwright/test";

/**
 * REQ-2205 / REQ-2213: typed filter errors, safe API-unavailable state,
 * empty results announced to assistive tech.
 *
 * Prefer text-scoped alerts: Next.js also mounts `#__next-route-announcer__`
 * with role=alert, so bare getByRole("alert") is ambiguous.
 */
test.describe("catalog error and empty states (REQ-2205, REQ-2213)", () => {
  test("unknown filter yields a typed error, not a full catalog", async ({ page }) => {
    await page.goto("/en/catalog?bogus=1&include_experimental=1");
    const alert = page.getByRole("alert").filter({
      hasText: /Invalid catalog filter|Некорректный фильтр/i,
    });
    await expect(alert).toBeVisible();
    await expect(alert.getByText(/Unknown filter|Неизвестный фильтр/i)).toBeVisible();
    await expect(page.getByRole("link", { name: "pytest-guard-skill" })).toHaveCount(0);
  });

  test("unavailable API yields a safe error without partial catalog data", async ({ page }) => {
    await page.goto("/en/catalog?include_experimental=1&q=__ai_stp_force_unavailable__");
    const alert = page.getByRole("alert").filter({
      hasText:
        /temporarily unavailable|временно недоступен|No data was fabricated|не подставлялись/i,
    });
    await expect(alert).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("link", { name: "pytest-guard-skill" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Catalog" })).toBeVisible();
  });

  test("empty catalog results are announced with role=status", async ({ page }) => {
    await page.goto("/en/catalog?q=definitely-no-such-object-zzzx");
    const empty = page.getByRole("status").filter({
      hasText: /No catalog objects match this query|Нет объектов каталога/i,
    });
    await expect(empty).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("link", { name: "pytest-guard-skill" })).toHaveCount(0);
  });
});
