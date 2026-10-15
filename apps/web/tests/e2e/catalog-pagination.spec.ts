import { expect, test } from "@playwright/test";

/**
 * REQ-2206 / SPEC-034: explicit page navigation, no duplicates across pages,
 * and separate component/setup resources.
 */
test.describe("catalog pagination (REQ-2206)", () => {
  test.beforeEach(async ({ page }) => {
    if (process.env["AI_STP_CORPORATE_E2E"] !== "offline") return;
    await page.goto("/en/login?returnTo=%2Fen%2Fcorporate%2Fcatalog");
    await page.getByRole("button", { name: /Continue with GitHub/i }).click();
    await page.waitForURL("**/en/corporate/catalog");
  });
  test("mixed catalog renders server pagination and preserves resource coordinates", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/en/catalog?resource=all&page_size=5&page=1");
    await expect(
      page.getByRole("heading", { level: 1, name: "Catalog", exact: true }),
    ).toBeVisible();
    const pager = page.getByRole("navigation", { name: "Pagination", exact: true });
    await expect(pager).toBeVisible();
    const next = pager.getByRole("link", { name: "2", exact: true });
    const href = await next.getAttribute("href");
    const target = new URL(href ?? "", page.url());
    expect(target.searchParams.get("resource")).toBe("all");
    expect(target.searchParams.get("page_size")).toBe("5");
    expect(target.searchParams.get("setups_page")).not.toBeNull();
    expect(target.searchParams.get("components_page")).not.toBeNull();
    await next.click();
    await expect(page).toHaveURL(target.toString());
    await expect(pager.getByRole("link", { name: "2", exact: true })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(errors).toEqual([]);
  });
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
