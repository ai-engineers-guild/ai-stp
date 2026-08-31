import { expect, test } from "@playwright/test";

test.describe("owner workspace smoke (SPEC-027)", () => {
  test("signed-in owner can open objects access reports", async ({ page }) => {
    await page.goto("/en/login");
    await page
      .getByRole("button", {
        name: /Continue with GitHub|\u0412\u043e\u0439\u0442\u0438 \u0447\u0435\u0440\u0435\u0437 GitHub/i,
      })
      .click();
    await expect(page).toHaveURL(/\/en\/account/);

    await page.goto("/en/objects");
    await expect(
      page.getByRole("heading", {
        name: /Your objects|\u0412\u0430\u0448\u0438 \u043e\u0431\u044a\u0435\u043a\u0442\u044b/i,
      }),
    ).toBeVisible();
    await expect(page.getByText(/Owned fixture|component_/i).first()).toBeVisible();

    await page.goto("/en/access");
    await expect(
      page.getByRole("heading", { name: /Access|\u0414\u043e\u0441\u0442\u0443\u043f/i }),
    ).toBeVisible();

    await page.goto("/en/reports");
    await expect(
      page.getByRole("heading", { name: /Reports|\u0416\u0430\u043b\u043e\u0431\u044b/i }),
    ).toBeVisible();
  });

  test("unauthenticated objects redirect without owned body", async ({ page }) => {
    await page.goto("/en/objects");
    await expect(page).toHaveURL(/\/en\/login/);
    await expect(page.getByText("Owned fixture component")).toHaveCount(0);
  });

  test("invitation accept page scrubs fragment token from history", async ({ page }) => {
    await page.goto("/en/login");
    await page
      .getByRole("button", {
        name: /Continue with GitHub|\u0412\u043e\u0439\u0442\u0438 \u0447\u0435\u0440\u0435\u0437 GitHub/i,
      })
      .click();
    await expect(page).toHaveURL(/\/en\/account/);

    const invitationId = "invite_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
    const secret = "fragment-secret-token-value";
    await page.goto(`/en/invitations/${invitationId}#token=${secret}`);
    await expect(
      page.getByRole("heading", {
        name: /Accept invitation|\u041f\u0440\u0438\u043d\u044f\u0442\u044c \u043f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u0435/i,
      }),
    ).toBeVisible();
    // Wait for client effect to capture the fragment into memory.
    await expect(
      page.getByRole("button", {
        name: /Accept invitation|\u041f\u0440\u0438\u043d\u044f\u0442\u044c \u043f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u0435/i,
      }),
    ).toBeVisible();
    // Component scrubs hash on mount.
    await expect.poll(() => page.url()).not.toContain(secret);
    await expect.poll(() => page.url()).not.toContain("#token=");

    const storage = await page.evaluate(() => ({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }));
    expect(JSON.stringify(storage)).not.toContain(secret);

    await page
      .getByRole("button", {
        name: /Accept invitation|\u041f\u0440\u0438\u043d\u044f\u0442\u044c \u043f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u0435/i,
      })
      .click();
    await expect(
      page.getByText(
        /Invitation accepted|\u041f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u0435 \u043f\u0440\u0438\u043d\u044f\u0442\u043e/i,
      ),
    ).toBeVisible();
  });

  test("publication plan review renders server plan state", async ({ page }) => {
    await page.goto("/en/login");
    await page
      .getByRole("button", {
        name: /Continue with GitHub|\u0412\u043e\u0439\u0442\u0438 \u0447\u0435\u0440\u0435\u0437 GitHub/i,
      })
      .click();
    await expect(page).toHaveURL(/\/en\/account/);

    await page.goto("/en/publications/plan_01JQZK7B8N4M6P2R9T5V0X3Y7Z");
    await expect(
      page.getByRole("heading", {
        name: /Publication plan|\u041f\u043b\u0430\u043d \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438/i,
      }),
    ).toBeVisible();
    await expect(page.getByText(/ready/i).first()).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: /Confirm publication|\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u044c \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u044e/i,
      }),
    ).toBeVisible();
  });
});
