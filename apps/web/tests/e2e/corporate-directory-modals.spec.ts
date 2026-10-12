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
    for (const resource of ["employees", "projects", "teams", "technologies"]) {
      await page.goto(`/en/corporate/${resource}`);
      const heading = page.locator("#main-content h1");
      const original = await heading.textContent();
      await page.locator(`a[href$="/corporate/${resource}/new"]`).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(heading).toHaveText(original ?? "");
      await page.getByRole("dialog").getByRole("button", { name: "Close", exact: true }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page).toHaveURL(new RegExp(`/corporate/${resource}$`));
      await page.locator('#main-content button[aria-label="More actions"]').first().click();
      await page.getByRole("menuitem", { name: "Edit", exact: true }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(heading).toHaveText(original ?? "");
      await page.getByRole("dialog").getByRole("button", { name: "Close", exact: true }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await page.evaluate(() => {
        sessionStorage.clear();
      });
      await page.goto(`/en/corporate/${resource}/new`);
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(heading).toHaveText(original ?? "");
      await page.getByRole("dialog").getByRole("button", { name: "Close", exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`/en/corporate/${resource}$`));
      await expect(page.getByRole("dialog")).toHaveCount(0);
    }
    await page.goto("/en/corporate/employees");
    for (const action of ["Manage access"]) {
      await page.locator('#main-content button[aria-label="More actions"]').first().click();
      await page.getByRole("menuitem", { name: action, exact: true }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(page.locator("#main-content h1")).toHaveText("Employees");
      await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page).toHaveURL(/\/corporate\/employees$/);
    }
    if (!(await page.getByRole("menu").isVisible()))
      await page.locator('#main-content button[aria-label="More actions"]').first().click();
    await page.getByRole("menuitem", { name: "Edit public presentation", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Save", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page).toHaveURL(/\/corporate\/employees$/);
  });
  test("saves employee edits and returns to the invoking directory", async ({ page }) => {
    await page.goto("/en/login?returnTo=%2Fen%2Fcorporate%2Femployees");
    await page.getByRole("button", { name: /Continue with GitHub/i }).click();
    await page.waitForURL("**/en/corporate/employees");
    const origin = page.url();
    await page.locator('#main-content button[aria-label="More actions"]').first().click();
    await page.getByRole("menuitem", { name: "Edit", exact: true }).click();
    const dialog = page.getByRole("dialog");
    const name = dialog.getByRole("textbox", { name: "Display name", exact: true });
    const original = await name.inputValue();
    const updated = `${original} modal regression`;
    await name.fill(updated);
    await dialog.getByRole("button", { name: "Save changes", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page).toHaveURL(origin);
    await expect(page.locator("#main-content").getByText(updated, { exact: true })).toBeVisible();
    await page.locator('#main-content button[aria-label="More actions"]').first().click();
    await page.getByRole("menuitem", { name: "Edit", exact: true }).click();
    await name.fill(original);
    await dialog.getByRole("button", { name: "Save changes", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator("#main-content").getByText(original, { exact: true })).toBeVisible();
  });
  test("creates reference entities in dialogs without replacing their page", async ({ page }) => {
    await page.goto("/en/login?returnTo=%2Fen%2Fcorporate%2Foverview");
    await page.getByRole("button", { name: /Continue with GitHub/i }).click();
    await page.waitForURL("**/en/corporate/overview");
    for (const [route, title] of [
      ["admin/technology-areas", "Create area"],
      ["admin/tech-categories", "Add category"],
      ["admin/job-titles", "Create job title"],
      ["organization/roles", "Create role"],
    ] as const) {
      await page.goto(`/en/corporate/${route}`);
      const origin = page.url();
      const heading = page.locator("#main-content h1");
      const name = await heading.textContent();
      await page.locator("#main-content").getByRole("button", { name: title, exact: true }).click();
      const dialog = page.getByRole("dialog", { name: title, exact: true });
      await expect(dialog).toBeVisible();
      await expect(heading).toHaveText(name ?? "");
      await expect(page).toHaveURL(origin);
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(page).toHaveURL(origin);
    }
  });
  test("renders reports once and limits landscape navigation to its three destinations", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 600 });
    await page.goto("/en/login?returnTo=%2Fen%2Fcorporate%2Foverview");
    await page.getByRole("button", { name: /Continue with GitHub/i }).click();
    await page.waitForURL("**/en/corporate/overview");
    const sidebar = page.locator('[data-ui="context-sidebar"]');
    await expect(sidebar.locator('a[href$="/corporate/reports"]')).toHaveCount(1);
    await expect(sidebar.locator('a[href$="/corporate/categories"]')).toHaveCount(0);
    await sidebar.getByRole("link", { name: "Reports", exact: true }).click();
    await expect(page).toHaveURL(/\/corporate\/reports$/);
    const before = await sidebar.boundingBox();
    await page.evaluate(() => {
      scrollTo(0, document.documentElement.scrollHeight);
    });
    expect(await page.evaluate(() => scrollY)).toBeGreaterThan(0);
    const after = await sidebar.boundingBox();
    expect(before).not.toBeNull();
    expect(after?.y).toBe(before?.y);
    expect(after?.height).toBe(before?.height);
    await expect(
      sidebar.getByRole("link", { name: "Administration", exact: true }),
    ).toBeInViewport();
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
