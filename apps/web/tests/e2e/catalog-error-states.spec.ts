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
      hasText:
        /Invalid catalog filter|\u041d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u044b\u0439 \u0444\u0438\u043b\u044c\u0442\u0440/i,
    });
    await expect(alert).toBeVisible();
    await expect(
      alert.getByText(
        /Unknown filter|\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u0444\u0438\u043b\u044c\u0442\u0440/i,
      ),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "pytest-guard-skill" })).toHaveCount(0);
  });

  test("unavailable API yields a safe error without partial catalog data", async ({ page }) => {
    await page.goto("/en/catalog?include_experimental=1&q=__ai_stp_force_unavailable__");
    const alert = page.getByRole("alert").filter({
      hasText:
        /temporarily unavailable|\u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d|No data was fabricated|\u043d\u0435 \u043f\u043e\u0434\u0441\u0442\u0430\u0432\u043b\u044f\u043b\u0438/i,
    });
    await expect(alert).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("link", { name: "pytest-guard-skill" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Catalog" })).toBeVisible();
  });

  test("empty catalog results are announced with role=status", async ({ page }) => {
    await page.goto("/en/catalog?q=definitely-no-such-object-zzzx");
    const empty = page.getByRole("status").filter({
      hasText:
        /No catalog objects match this query|\u041d\u0435\u0442 \u043e\u0431\u044a\u0435\u043a\u0442\u043e\u0432 \u043a\u0430\u0442\u0430\u043b\u043e\u0433\u0430/i,
    });
    await expect(empty).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("link", { name: "pytest-guard-skill" })).toHaveCount(0);
  });
});
