import { expect, test, type Page } from "@playwright/test";

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

test.describe("device approval says which refusal it is", () => {
  // `description` on the error panel was `sp.status`, so every failure read
  // "error" under "Could not approve this code" — the same words for a
  // mistyped code, one that had timed out, one already used, and a rejected
  // request. A previous session spent a working day on "the button fires every
  // other time" with nothing on the page to say which of the four it was.
  const refusals = [
    { reason: "unknown", says: /No pending sign-in uses this code/i },
    { reason: "expired", says: /This code has expired/i },
    { reason: "resolved", says: /already used/i },
    { reason: "csrf", says: /went stale while it was open/i },
    { reason: "failed", says: /did not reach the service/i },
  ];

  // `role="alert"` alone also matches Next.js's route announcer. The panel
  // carries `data-kind`, which is what it is for.
  async function signIn(page: Page) {
    await page.goto("/en/login");
    await page.getByRole("button", { name: /Continue with GitHub|Войти через GitHub/i }).click();
    await expect(page).toHaveURL(/\/en\/account/);
  }

  for (const { reason, says } of refusals) {
    test(`the page names the "${reason}" refusal`, async ({ page }) => {
      await signIn(page);
      await page.goto(`/en/device-login?status=error&reason=${reason}`);
      await expect(page.locator('[data-kind="error"]')).toContainText(says);
    });
  }

  test("the five refusals do not share one message", async ({ page }) => {
    // The property that was actually broken. Asserting each sentence alone
    // would still pass if every reason resolved to the same key, which is the
    // shape the defect had: one `error` string answering four questions.
    await signIn(page);
    const seen: string[] = [];
    for (const { reason } of refusals) {
      await page.goto(`/en/device-login?status=error&reason=${reason}`);
      seen.push(((await page.locator('[data-kind="error"]').textContent()) ?? "").trim());
    }
    expect(new Set(seen).size).toBe(refusals.length);
  });

  test("an unrecognised reason still reads as a sentence", async ({ page }) => {
    await signIn(page);
    await page.goto("/en/device-login?status=error&reason=../../etc/passwd");
    await expect(page.locator('[data-kind="error"]')).toContainText(/did not reach the service/i);
  });
});
