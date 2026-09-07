import { expect, test } from "@playwright/test";

test("returns from an object to the same catalog filters and view", async ({ page }) => {
  await page.goto("/en/catalog?resource=setups&include_experimental=1&view=list&sort=updated_at");
  const before = new URL(page.url());
  const link = page.locator('a[href*="/catalog/setups/"][href*="return_to="]').first();
  await expect(link).toBeVisible();
  await link.click();
  await page.getByRole("link", { name: "Back to catalog" }).click();
  await expect(page).toHaveURL((url) => url.pathname === before.pathname);
  const after = new URL(page.url());
  expect(after.pathname).toBe(before.pathname);
  for (const key of ["resource", "include_experimental", "view", "sort"]) {
    expect(after.searchParams.get(key)).toBe(before.searchParams.get(key));
  }
});
