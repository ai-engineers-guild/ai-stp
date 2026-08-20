import { expect, test } from "@playwright/test";

test.describe("login + devices smoke (REQ-2311)", () => {
  test("sign in, open devices, revoke confirmation", async ({ page }) => {
    await page.goto("/en/login");
    await page.getByRole("button", { name: /Continue with GitHub|Войти через GitHub/i }).click();
    await expect(page).toHaveURL(/\/en\/account/);
    await expect(page.getByText(/account_01JQZK7B8N4M6P2R9T5V0X3Y7Z/)).toBeVisible();

    // Browser storage must not hold long-lived provider tokens (REQ-2307).
    const storage = await page.evaluate(() => ({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }));
    expect(JSON.stringify(storage)).not.toMatch(/access_token|refresh_token|oauth/i);

    await page.goto("/en/devices");
    await expect(page.getByRole("heading", { name: "fixture-device" })).toBeVisible();
    await expect(page.getByText("device_01JQZK7B8N4M6P2R9T5V0X3Y70")).toBeVisible();
    await page.getByLabel("Device code").fill("ABCD-EFGH");
    await page.getByRole("button", { name: "Confirm device" }).click();
    await expect(page).toHaveURL(/\/en\/devices\?status=ok/);
    await expect(page.getByText("Device approved")).toBeVisible();
    await page
      .getByRole("button", { name: /Revoke|Отозвать/i })
      .first()
      .click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /Revoke this device|Отозвать это устройство/i }),
    ).toBeVisible();
  });

  test("unauthenticated devices redirect without protected body", async ({ page }) => {
    await page.goto("/en/devices");
    await expect(page).toHaveURL(/\/en\/login/);
    await expect(page.getByText("fixture-device")).toHaveCount(0);
  });
});
