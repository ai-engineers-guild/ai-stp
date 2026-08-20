import { expect, type Page, test } from "@playwright/test";

const stableId = "setup_01JQZK7B8N4M6P2R9T5V0X3YC2";

async function expectContextBudgetInRightRail(page: Page) {
  const rail = page.locator('[data-ui="component-detail-rail"]');
  const main = page.locator('[data-ui="component-detail-main"]');
  await expect(rail.locator('[data-ui="catalog-context-budget"]')).toHaveCount(1);
  await expect(main.locator('[data-ui="catalog-context-budget"]')).toHaveCount(0);
  await expect(rail.getByRole("heading", { name: "Author" })).toBeVisible();
  await expect(rail.getByRole("heading", { name: /Context budget/ })).toBeVisible();
  await expect(rail.getByRole("heading", { name: "Use via CLI" })).toBeVisible();
  await expect(rail.getByRole("heading", { name: /Version history/ })).toBeVisible();

  const documentOrder = await page.evaluate(() => {
    const railNode = document.querySelector('[data-ui="component-detail-rail"]');
    if (!railNode) return { found: [false, false, false, false], precedes: false };
    const author = railNode.querySelector('[data-ui="catalog-author-link"]');
    const budget = railNode.querySelector('[data-ui="catalog-context-budget"]');
    const install = [...railNode.querySelectorAll("h2, h3")].find((node) =>
      node.textContent.includes("Use via CLI"),
    );
    const history = [...railNode.querySelectorAll("h2, h3")].find((node) =>
      /Version history/.test(node.textContent),
    );
    const found = [author, budget, install, history].map((node) => node !== null);
    if (!author || !budget || !install || !history) {
      return { found, precedes: false };
    }
    const following = Node.DOCUMENT_POSITION_FOLLOWING;
    return {
      found,
      precedes:
        Boolean(author.compareDocumentPosition(budget) & following) &&
        Boolean(budget.compareDocumentPosition(install) & following) &&
        Boolean(install.compareDocumentPosition(history) & following),
    };
  });
  expect(documentOrder.found).toEqual([true, true, true, true]);
  expect(documentOrder.precedes).toBe(true);

  const authorTop = await rail
    .locator('[data-ui="catalog-author-link"]')
    .evaluate((node) => node.getBoundingClientRect().top);
  const budgetTop = await rail
    .locator('[data-ui="catalog-context-budget"]')
    .evaluate((node) => node.getBoundingClientRect().top);
  const installTop = await rail
    .getByRole("heading", { name: "Use via CLI" })
    .evaluate((node) => node.getBoundingClientRect().top);
  const historyTop = await rail
    .getByRole("heading", { name: /Version history/ })
    .evaluate((node) => node.getBoundingClientRect().top);
  expect(authorTop).toBeLessThan(budgetTop);
  expect(budgetTop).toBeLessThan(installTop);
  expect(installTop).toBeLessThan(historyTop);

  const viewport = page.viewportSize();
  if (viewport && viewport.width >= 1024) {
    const mainBox = await main.boundingBox();
    const railBox = await rail.boundingBox();
    const budgetBox = await rail.locator('[data-ui="catalog-context-budget"]').boundingBox();
    expect(mainBox).toBeTruthy();
    expect(railBox).toBeTruthy();
    expect(budgetBox).toBeTruthy();
    if (mainBox && railBox && budgetBox) {
      expect(railBox.x).toBeGreaterThan(mainBox.x + mainBox.width - 1);
      expect(budgetBox.x).toBeGreaterThan(mainBox.x + mainBox.width - 1);
    }
  }
}

test.describe("setup detail composition", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/en/catalog/setups/${stableId}`);
    await expect(
      page.getByRole("heading", { level: 1, name: "river-docs-workspace" }),
    ).toBeVisible();
  });

  test("groups identity, pinned composition, compatibility, author and history", async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await expect(page.getByRole("heading", { name: "Description" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Pinned components/ })).toBeVisible();
    await page.getByRole("button", { name: /Pinned components/ }).click();
    await expect(page.getByRole("heading", { name: /Compatibility/ })).toBeVisible();
    await expectContextBudgetInRightRail(page);
    await expect(page.getByText("ai-stp select impact")).toHaveCount(0);
    await expect(page.locator('a[href^="/en/catalog/components/"]')).toHaveCount(4);

    await expect(page.locator('[data-ui="component-overflow"]')).toHaveClass(/right-0/);
    await page.getByRole("button", { name: "More actions" }).click();
    await page.getByRole("menuitem", { name: "Copy ID" }).click();
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(stableId);
    await page.getByRole("button", { name: /Like ·/ }).click();
    await expect(page.getByRole("button", { name: /Liked ·/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await page.getByRole("button", { name: "More actions" }).click();
    await page.getByRole("menuitem", { name: "Report setup" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.locator('input[name="subject"]')).toHaveValue(new RegExp(stableId));
  });

  test("keeps the primary layout usable on a narrow viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: "More actions" })).toBeVisible();
    await expectContextBudgetInRightRail(page);
    const width = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(width.scroll).toBeLessThanOrEqual(width.client);
  });
});
