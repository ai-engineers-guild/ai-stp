import { expect, test } from "@playwright/test";
const mode = process.env["AI_STP_CORPORATE_E2E"];
test.describe("corporate directory interactions", () => {
  test.skip(
    mode !== "offline",
    "Uses the corporate fixture transport; authorization is checked by backend integration tests.",
  );
  test("keeps create and organizational edit on their originating directory", async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto("/en/login?returnTo=%2Fen%2Fcorporate%2Foverview");
    await page.getByRole("button", { name: /Continue with GitHub/i }).click();
    await page.waitForURL("**/en/corporate/overview");
    for (const resource of ["employees", "projects", "teams"]) {
      await page.goto(`/en/corporate/${resource}`);
      const heading = page.locator("#main-content h1");
      const original = await heading.textContent();
      await page.locator(`a[href$="/corporate/${resource}/new"]`).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(heading).toHaveText(original ?? "");
      await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page).toHaveURL(new RegExp(`/corporate/${resource}$`));
      await page.locator('#main-content button[aria-label="More actions"]').first().click();
      await page.getByRole("menuitem", { name: "Edit", exact: true }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(heading).toHaveText(original ?? "");
      await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
    }
    await page.goto("/en/corporate/employees");
    for (const action of ["Edit public presentation", "Manage access"]) {
      await page.locator('#main-content button[aria-label="More actions"]').first().click();
      await page.getByRole("menuitem", { name: action, exact: true }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(page.locator("#main-content h1")).toHaveText("Employees");
      await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page).toHaveURL(/\/corporate\/employees$/);
    }
  });
  test("renders reports once and limits landscape navigation to its three destinations", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/en/login?returnTo=%2Fen%2Fcorporate%2Foverview");
    await page.getByRole("button", { name: /Continue with GitHub/i }).click();
    await page.waitForURL("**/en/corporate/overview");
    const sidebar = page.locator('[data-ui="context-sidebar"]');
    await expect(sidebar.locator('a[href$="/corporate/reports"]')).toHaveCount(1);
    await expect(sidebar.locator('a[href$="/corporate/categories"]')).toHaveCount(0);
    await sidebar.getByRole("link", { name: "Reports", exact: true }).click();
    await expect(page).toHaveURL(/\/corporate\/reports$/);
    await page.goto("/en/corporate/technology-landscape");
    await expect(sidebar.locator('a[href$="/corporate/categories"]')).toHaveCount(0);
    for (const [route, name] of [
      ["technology-landscape", "Technology map"],
      ["technology-scans", "Scans"],
      ["technology-mappings", "Mapping"],
    ] as const) {
      const link = sidebar.getByRole("link", { name, exact: true });
      await expect(link).toHaveCount(1);
      await link.click();
      await expect(page).toHaveURL(new RegExp(`/corporate/${route}$`));
    }
  });
});
