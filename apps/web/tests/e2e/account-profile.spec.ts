import { expect, test } from "@playwright/test";

/**
 * SPEC-028: owner profile editor (draft/publish) under mock auth for e2e.
 */
test.describe("account profile (SPEC-028)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/en/login");
    await page.getByRole("button", { name: /Continue with GitHub|Войти через GitHub/i }).click();
    await expect(page).toHaveURL(/\/en\/account/);
  });

  test("opens editor with save draft, publish, preview and avatar controls", async ({ page }) => {
    await page.goto("/en/account/profile");
    await expect(
      page.getByRole("heading", { name: /Public profile|Публичный профиль/i }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /^Save$|^Сохранить$/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^(Publish|Опубликовать)$/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Preview|Предпросмотр/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Upload photo|Загрузить фото/i })).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Use from GitHub|Взять из GitHub/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Use from Google|Взять из Google/i }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /Plain text|Текст/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Rendered|Рендер/i })).toBeVisible();
  });

  test("saves draft and opens the routed preview", async ({ page }) => {
    await page.goto("/en/account/profile");
    const name = page.getByLabel(/Display name/i);
    await name.fill("E2E Profile Name");
    await page.getByRole("button", { name: /^Save$|^Сохранить$/i }).click();
    await expect(page.getByText(/Draft saved|Черновик сохранён/i)).toBeVisible();
    await page.getByRole("link", { name: /Preview|Предпросмотр/i }).click();
    await expect(page).toHaveURL(/\/account\/profile\/preview/);
    await expect(
      page.getByText(/Preview — temporary and not saved|Предпросмотр — временно и без сохранения/i),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "E2E Profile Name" })).toBeVisible();
  });

  test("authenticated account exposes profile navigation and logout", async ({ page }) => {
    const accountControl = page.locator('[data-ui="nav-account"]');
    await expect(accountControl).toBeVisible();
    await expect(page.getByRole("link", { name: /Sign in|Войти/i })).toHaveCount(0);
    await accountControl.click();
    const menu = page.getByRole("menu");
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: /Profile|Профиль/i })).toHaveAttribute(
      "href",
      /\/account$/,
    );
    await expect(menu.getByRole("menuitem", { name: /My objects|Мои объекты/i })).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: /Devices|Устройства/i })).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: /Access|Доступ/i })).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: /Sign out|Выйти/i })).toBeVisible();
  });

  test("uploads an avatar and includes its binding in the saved draft", async ({ page }) => {
    await page.goto("/en/account/profile");
    await page.locator('input[type="file"]').setInputFiles("public/brand/icon-32.png");
    await expect(page.getByText(/Avatar ready|Avatar готов/i)).toBeVisible();
    await expect(page.locator("section img").first()).toHaveAttribute("src", /^data:image\/png/);
    await page.getByRole("button", { name: /^Save$|^Сохранить$/i }).click();
    await expect(page.getByText(/Draft saved|Черновик сохранён/i)).toBeVisible();
  });

  test("previews unsaved form changes and offers account-id copy without exposing the id", async ({
    page,
  }) => {
    await page.goto("/en/account/profile");
    await page.getByLabel(/Display name/i).fill("Unsaved Preview Name");
    await page.getByRole("link", { name: /Preview|Предпросмотр/i }).click();
    await expect(page.getByRole("heading", { name: "Unsaved Preview Name" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Copy|Копировать/i })).toBeVisible();
    await expect(page.getByText(/^account_/)).toHaveCount(0);
  });

  test("keeps unsaved fields after returning from preview", async ({ page }) => {
    await page.goto("/en/account/profile");
    await page.getByLabel(/Display name/i).fill("Unsaved Round Trip");
    await page
      .getByRole("textbox", { name: /Short bio|Краткое описание/i })
      .fill("Unsaved bio survives preview navigation");
    await page.getByRole("button", { name: /Add|Добавить/i }).click();
    const linkRows = page.locator("section").filter({ hasText: /^Links/ });
    await linkRows
      .getByLabel(/Label|Метка/i)
      .last()
      .fill("Docs");
    await linkRows.getByLabel(/URL/i).last().fill("https://example.com/docs");

    await page.getByRole("link", { name: /Preview|Предпросмотр/i }).click();
    await expect(page.getByRole("heading", { name: "Unsaved Round Trip" })).toBeVisible();
    await page.getByRole("link", { name: /Edit public profile|Редактировать/i }).click();

    await expect(page.getByLabel(/Display name/i)).toHaveValue("Unsaved Round Trip");
    await expect(page.getByRole("textbox", { name: /Short bio|Краткое описание/i })).toHaveValue(
      "Unsaved bio survives preview navigation",
    );
    await expect(linkRows.getByLabel(/Label|Метка/i).last()).toHaveValue("Docs");
    await expect(linkRows.getByLabel(/URL/i).last()).toHaveValue("https://example.com/docs");
  });

  test("publishes current fields and keeps them after reload", async ({ page }) => {
    await page.goto("/en/account/profile");
    await page.getByLabel(/Display name/i).fill("Published E2E Profile");
    await page.getByRole("button", { name: /^(Publish|Опубликовать)$/i }).click();
    await expect(page.getByRole("status")).toHaveText(/Published|Опубликован/i);
    await page.reload();
    await expect(page.getByLabel(/Display name/i)).toHaveValue("Published E2E Profile");
  });

  test("renders rich safe Markdown with a heading, table, emoji, and annotated link", async ({
    page,
  }) => {
    await page.goto("/en/account/profile");
    await page
      .getByRole("textbox", { name: /Short bio|Краткое описание/i })
      .fill(
        '## Toolbox 🧰\n\n| Tool | State |\n| --- | --- |\n| Codex | Ready |\n\n[Open docs](https://example.com/docs "Annotated docs")',
      );
    await page.getByRole("button", { name: /Rendered|Рендер/i }).click();
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
