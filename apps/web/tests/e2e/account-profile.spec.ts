import { expect, test } from "@playwright/test";

/**
 * SPEC-028: owner profile editor (draft/publish) under mock auth for e2e.
 */
test.describe("account profile (SPEC-028)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/en/login");
    await page
      .getByRole("button", {
        name: /Continue with GitHub|\u0412\u043e\u0439\u0442\u0438 \u0447\u0435\u0440\u0435\u0437 GitHub/i,
      })
      .click();
    await expect(page).toHaveURL(/\/en\/account/);
  });

  test("opens editor with save draft, publish, preview and avatar controls", async ({ page }) => {
    await page.goto("/en/account/profile");
    await expect(
      page.getByRole("heading", {
        name: /Public profile|\u041f\u0443\u0431\u043b\u0438\u0447\u043d\u044b\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c/i,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: /^Save$|^\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c$/i,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: /^(Publish|\u041e\u043f\u0443\u0431\u043b\u0438\u043a\u043e\u0432\u0430\u0442\u044c)$/i,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", {
        name: /Preview|\u041f\u0440\u0435\u0434\u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440/i,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: /Upload photo|\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0444\u043e\u0442\u043e/i,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: /Use from GitHub|\u0412\u0437\u044f\u0442\u044c \u0438\u0437 GitHub/i,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: /Use from Google|\u0412\u0437\u044f\u0442\u044c \u0438\u0437 Google/i,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Plain text|\u0422\u0435\u043a\u0441\u0442/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Rendered|\u0420\u0435\u043d\u0434\u0435\u0440/i }),
    ).toBeVisible();
  });

  test("saves draft and opens the routed preview", async ({ page }) => {
    await page.goto("/en/account/profile");
    const name = page.getByLabel(/Display name/i);
    await name.fill("E2E Profile Name");
    await page
      .getByRole("button", {
        name: /^Save$|^\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c$/i,
      })
      .click();
    await expect(
      page.getByText(
        /Draft saved|\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d/i,
      ),
    ).toBeVisible();
    await page
      .getByRole("link", {
        name: /Preview|\u041f\u0440\u0435\u0434\u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440/i,
      })
      .click();
    await expect(page).toHaveURL(/\/account\/profile\/preview/);
    await expect(
      page.getByText(
        /Preview — temporary and not saved|\u041f\u0440\u0435\u0434\u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440 — \u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e \u0438 \u0431\u0435\u0437 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0438\u044f/i,
      ),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "E2E Profile Name" })).toBeVisible();
  });

  test("authenticated account exposes profile navigation and logout", async ({ page }) => {
    const accountControl = page.locator('[data-ui="nav-account"]');
    await expect(accountControl).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Sign in|\u0412\u043e\u0439\u0442\u0438/i }),
    ).toHaveCount(0);
    await accountControl.click();
    const menu = page.getByRole("menu");
    await expect(menu).toBeVisible();
    await expect(
      menu.getByRole("menuitem", { name: /Profile|\u041f\u0440\u043e\u0444\u0438\u043b\u044c/i }),
    ).toHaveAttribute("href", /\/account$/);
    await expect(
      menu.getByRole("menuitem", {
        name: /My objects|\u041c\u043e\u0438 \u043e\u0431\u044a\u0435\u043a\u0442\u044b/i,
      }),
    ).toBeVisible();
    await expect(
      menu.getByRole("menuitem", {
        name: /Devices|\u0423\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0430/i,
      }),
    ).toBeVisible();
    await expect(
      menu.getByRole("menuitem", { name: /Access|\u0414\u043e\u0441\u0442\u0443\u043f/i }),
    ).toBeVisible();
    await expect(
      menu.getByRole("menuitem", { name: /Sign out|\u0412\u044b\u0439\u0442\u0438/i }),
    ).toBeVisible();
  });

  test("uploads an avatar and includes its binding in the saved draft", async ({ page }) => {
    await page.goto("/en/account/profile");
    const uploaded = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/account/avatar",
    );
    await page.locator('input[type="file"]').setInputFiles("public/brand/icon-32.png");
    expect((await uploaded).status()).toBe(201);
    await expect(
      page.getByText(/Avatar ready|Avatar \u0433\u043e\u0442\u043e\u0432/i),
    ).toBeVisible();
    await expect(page.locator("section img").first()).toHaveAttribute("src", /^data:image\/png/);
    await page
      .getByRole("button", {
        name: /^Save$|^\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c$/i,
      })
      .click();
    await expect(
      page.getByText(
        /Draft saved|\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d/i,
      ),
    ).toBeVisible();
  });

  test("previews unsaved form changes and offers account-id copy without exposing the id", async ({
    page,
  }) => {
    await page.goto("/en/account/profile");
    await page.getByLabel(/Display name/i).fill("Unsaved Preview Name");
    await page
      .getByRole("link", {
        name: /Preview|\u041f\u0440\u0435\u0434\u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440/i,
      })
      .click();
    await expect(page.getByRole("heading", { name: "Unsaved Preview Name" })).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: /Copy|\u041a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c/i,
      }),
    ).toBeVisible();
    await expect(page.getByText(/^account_/)).toHaveCount(0);
  });

  test("keeps unsaved fields after returning from preview", async ({ page }) => {
    await page.goto("/en/account/profile");
    await page.getByLabel(/Display name/i).fill("Unsaved Round Trip");
    await page
      .getByRole("textbox", {
        name: /Short bio|\u041a\u0440\u0430\u0442\u043a\u043e\u0435 \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435/i,
      })
      .fill("Unsaved bio survives preview navigation");
    await page
      .getByRole("button", { name: /Add|\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c/i })
      .click();
    const linkRows = page.locator("section").filter({ hasText: /^Links/ });
    await linkRows
      .getByLabel(/Label|\u041c\u0435\u0442\u043a\u0430/i)
      .last()
      .fill("Docs");
    await linkRows.getByLabel(/URL/i).last().fill("https://example.com/docs");

    await page
      .getByRole("link", {
        name: /Preview|\u041f\u0440\u0435\u0434\u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440/i,
      })
      .click();
    await expect(page.getByRole("heading", { name: "Unsaved Round Trip" })).toBeVisible();
    await page
      .getByRole("link", {
        name: /Edit public profile|\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c/i,
      })
      .click();

    await expect(page.getByLabel(/Display name/i)).toHaveValue("Unsaved Round Trip");
    await expect(
      page.getByRole("textbox", {
        name: /Short bio|\u041a\u0440\u0430\u0442\u043a\u043e\u0435 \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435/i,
      }),
    ).toHaveValue("Unsaved bio survives preview navigation");
    await expect(linkRows.getByLabel(/Label|\u041c\u0435\u0442\u043a\u0430/i).last()).toHaveValue(
      "Docs",
    );
    await expect(linkRows.getByLabel(/URL/i).last()).toHaveValue("https://example.com/docs");
  });

  test("publishes current fields and keeps them after reload", async ({ page }) => {
    await page.goto("/en/account/profile");
    await page.getByLabel(/Display name/i).fill("Published E2E Profile");
    await page
      .getByRole("button", {
        name: /^(Publish|\u041e\u043f\u0443\u0431\u043b\u0438\u043a\u043e\u0432\u0430\u0442\u044c)$/i,
      })
      .click();
    await expect(page.getByRole("status")).toHaveText(
      /Published|\u041e\u043f\u0443\u0431\u043b\u0438\u043a\u043e\u0432\u0430\u043d/i,
    );
    await page.reload();
    await expect(page.getByLabel(/Display name/i)).toHaveValue("Published E2E Profile");
  });

  test("renders rich safe Markdown with a heading, table, emoji, and annotated link", async ({
    page,
  }) => {
    await page.goto("/en/account/profile");
    await page
      .getByRole("textbox", {
        name: /Short bio|\u041a\u0440\u0430\u0442\u043a\u043e\u0435 \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u0435/i,
      })
      .fill(
        '## Toolbox 🧰\n\n| Tool | State |\n| --- | --- |\n| Codex | Ready |\n\n[Open docs](https://example.com/docs "Annotated docs")',
      );
    await page
      .getByRole("button", { name: /Rendered|\u0420\u0435\u043d\u0434\u0435\u0440/i })
      .click();
    await expect(page.getByRole("heading", { name: "Toolbox 🧰" })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByRole("cell", { name: "Codex" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open docs" })).toHaveAttribute(
      "href",
      "https://example.com/docs",
    );
    await expect(page.getByRole("link", { name: "Open docs" })).toHaveAttribute(
      "title",
      "Annotated docs",
    );
  });
});
