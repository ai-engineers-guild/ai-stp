import { expect, test } from "@playwright/test";

/**
 * REQ-2206 / SPEC-034: explicit page navigation, no duplicates across pages,
 * and separate component/setup resources.
 */
test.describe("catalog pagination (REQ-2206)", () => {
  test("components expose explicit page links and do not duplicate adjacent pages", async ({
    page,
  }) => {
    await page.goto("/en/catalog?resource=components&include_experimental=1&page_size=5&page=1");
    await expect(
      page.getByRole("heading", { level: 1, name: "Catalog", exact: true }),
    ).toBeVisible();

    const firstPageNames = await page.locator("article[data-kind] h3 a").allTextContents();
    expect(firstPageNames.length).toBeGreaterThan(0);
    expect(firstPageNames.length).toBeLessThanOrEqual(5);

    const secondPage = page.locator('nav[aria-label="Pagination"] a[href*="page=2"]');
    await expect(secondPage).toBeVisible({ timeout: 15_000 });
    await secondPage.click();
    await page.waitForURL((url) => url.searchParams.get("page") === "2");
    expect(new URL(page.url()).searchParams.get("cursor")).toBeNull();
    const secondPageNames = await page.locator("article[data-kind] h3 a").allTextContents();
    expect(secondPageNames.length).toBeGreaterThan(0);

    const overlap = firstPageNames.filter((name) => secondPageNames.includes(name));
    expect(overlap).toEqual([]);
  });

  test("setups resource is separate from components", async ({ page }) => {
    await page.goto("/en/catalog?resource=setups&page_size=5");
    await expect(
      page.getByRole("heading", { level: 1, name: "Catalog", exact: true }),
    ).toBeVisible();

    const setupCard = page.getByRole("link", { name: "python-ci-workspace" });
    await expect(setupCard).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("link", { name: "pytest-guard-skill" })).toHaveCount(0);

    await page.goto("/en/catalog?resource=components&page_size=5");
    await expect(page.getByRole("link", { name: "pytest-guard-skill" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("link", { name: "python-ci-workspace" })).toHaveCount(0);
  });
});
