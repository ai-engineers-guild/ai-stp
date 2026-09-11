import { expect, test } from "@playwright/test";

test("human and machine shells do not expose a selectable context", async ({ page }) => {
  for (const path of ["/en/catalog", "/en/ai/catalog"]) {
    await page.goto(path);
    await expect(page.locator('[data-ui="product-context-switcher"]')).toHaveCount(0);
    await expect(page.locator('[data-ui="product-context-navigation"]')).toHaveCount(0);
    await expect(page.getByText("Context unavailable", { exact: true })).toHaveCount(0);
  }
});
