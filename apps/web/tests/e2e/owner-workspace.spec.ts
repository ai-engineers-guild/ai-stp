import { expect, test } from "@playwright/test";

test.describe("owner workspace smoke (SPEC-027)", () => {
  test("signed-in owner can open objects access reports", async ({ page }) => {
    await page.goto("/en/login");
    await page.getByRole("button", { name: /Continue with GitHub|Войти через GitHub/i }).click();
    await expect(page).toHaveURL(/\/en\/account/);

    await page.goto("/en/objects");
    await expect(page.getByRole("heading", { name: /Your objects|Ваши объекты/i })).toBeVisible();
    await expect(page.getByText(/Owned fixture|component_/i).first()).toBeVisible();

    await page.goto("/en/access");
    await expect(page.getByRole("heading", { name: /Access|Доступ/i })).toBeVisible();

    await page.goto("/en/reports");
    await expect(page.getByRole("heading", { name: /Reports|Жалобы/i })).toBeVisible();
  });

  test("unauthenticated objects redirect without owned body", async ({ page }) => {
    await page.goto("/en/objects");
    await expect(page).toHaveURL(/\/en\/login/);
    await expect(page.getByText("Owned fixture component")).toHaveCount(0);
  });

  test("invitation accept page scrubs fragment token from history", async ({ page }) => {
    await page.goto("/en/login");
    await page.getByRole("button", { name: /Continue with GitHub|Войти через GitHub/i }).click();
    await expect(page).toHaveURL(/\/en\/account/);

    const invitationId = "invite_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
    const secret = "fragment-secret-token-value";
    await page.goto(`/en/invitations/${invitationId}#token=${secret}`);
    await expect(
      page.getByRole("heading", { name: /Accept invitation|Принять приглашение/i }),
    ).toBeVisible();
    // Wait for client effect to capture the fragment into memory.
    await expect(
      page.getByRole("button", { name: /Accept invitation|Принять приглашение/i }),
    ).toBeVisible();
    // Component scrubs hash on mount.
    await expect.poll(() => page.url()).not.toContain(secret);
    await expect.poll(() => page.url()).not.toContain("#token=");

    const storage = await page.evaluate(() => ({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }));
    expect(JSON.stringify(storage)).not.toContain(secret);

    await page.getByRole("button", { name: /Accept invitation|Принять приглашение/i }).click();
    await expect(page.getByText(/Invitation accepted|Приглашение принято/i)).toBeVisible();
  });

  test("publication plan review renders server plan state", async ({ page }) => {
    await page.goto("/en/login");
    await page.getByRole("button", { name: /Continue with GitHub|Войти через GitHub/i }).click();
    await expect(page).toHaveURL(/\/en\/account/);

    await page.goto("/en/publications/plan_01JQZK7B8N4M6P2R9T5V0X3Y7Z");
    await expect(
      page.getByRole("heading", { name: /Publication plan|План публикации/i }),
    ).toBeVisible();
    await expect(page.getByText(/ready/i).first()).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Confirm publication|Подтвердить публикацию/i }),
    ).toBeVisible();
  });
});
