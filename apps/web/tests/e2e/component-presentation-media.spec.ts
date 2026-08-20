import { expect, test, type Page } from "@playwright/test";

import { FIXTURE_COMPONENT_ID } from "../../src/mocks/fixtures/catalog-ids";

async function selectUploadSource(page: Page): Promise<void> {
  const sourceSelect = page
    .locator("select")
    .filter({ has: page.locator('option[value="upload"]') })
    .first();
  await sourceSelect.selectOption("upload");
  await expect(page.locator('input[type="file"]').first()).toBeAttached({ timeout: 10_000 });
}

/**
 * Owner component presentation editor: upload, preview, save (SPEC-035 / REQ-3513).
 * Runs against the Playwright mock-auth standalone server.
 */
test.describe("component presentation media editor", () => {
  test.describe.configure({ timeout: 60_000 });

  test.beforeEach(async ({ page }) => {
    await page.goto("/en/login");
    await page.getByRole("button", { name: /Continue with GitHub|Войти через GitHub/i }).click();
    await expect(page).toHaveURL(/\/en\/account/);
  });

  test("uploads image media, shows preview, and saves presentation", async ({ page }) => {
    await page.goto(`/en/objects/component/${FIXTURE_COMPONENT_ID}/edit`);
    await expect(
      page.getByRole("heading", { name: /Edit bio and media|Изменить био и медиа/i }),
    ).toBeVisible();
    await expect(page.getByText(/JPEG, PNG, WebP, GIF, MP4 or WebM/i)).toBeVisible();

    await selectUploadSource(page);
    await page.locator('input[type="file"]').first().setInputFiles("public/brand/icon-32.png");
    await expect(page.locator("img[src^='data:image']").first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByText(/File uploaded and ready|Файл загружен и готов/i).first(),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('input[value*="/v1/media/component/"]')).toHaveCount(0);

    await page
      .getByLabel(/Alternative text|Альтернативный текст/i)
      .first()
      .fill("E2E uploaded cover");
    await page.locator("#presentation-bio").fill("E2E presentation bio with uploaded media");

    await page.getByRole("button", { name: /Save presentation|Сохранить представление/i }).click();
    await expect(page.getByText(/Presentation saved|Представление сохранено/i).first()).toBeVisible(
      { timeout: 15_000 },
    );

    await page.reload();
    await expect(page.locator("#presentation-bio")).toHaveValue(
      "E2E presentation bio with uploaded media",
    );
    await expect(page.getByLabel(/Alternative text|Альтернативный текст/i).first()).toHaveValue(
      "E2E uploaded cover",
    );
    await expect(
      page.getByText(/File uploaded and ready|Файл загружен и готов|Ready|Готово/i).first(),
    ).toBeVisible();
  });

  test("rejects unsupported client-side mime before upload", async ({ page }) => {
    await page.goto(`/en/objects/component/${FIXTURE_COMPONENT_ID}/edit`);
    await selectUploadSource(page);

    await page
      .locator('input[type="file"]')
      .first()
      .setInputFiles({
        name: "evil.svg",
        mimeType: "image/svg+xml",
        buffer: Buffer.from("<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
      });

    await expect(
      page.getByText(/Unsupported file type|Неподдерживаемый тип файла/i).first(),
    ).toBeVisible();
  });

  test("shows upload failure and recovery without treating preview as saved", async ({ page }) => {
    await page.goto(`/en/objects/component/${FIXTURE_COMPONENT_ID}/edit`);
    await selectUploadSource(page);

    let postCount = 0;
    await page.route(`**/api/objects/component/${FIXTURE_COMPONENT_ID}/media`, async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      postCount += 1;
      if (postCount === 1) {
        await route.fulfill({
          status: 502,
          contentType: "application/json",
          body: JSON.stringify({ message: "component media upload failed" }),
        });
        return;
      }
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: 1,
          media_id: "media_e2e_retry",
          kind: "image",
          public_url: "/v1/media/component/media_e2e_retry",
          state: "ready",
        }),
      });
    });

    await page.locator('input[type="file"]').first().setInputFiles("public/brand/icon-32.png");
    await expect(page.locator("img[src^='data:image']").first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page
        .getByText(/component media upload failed|Could not upload|Не удалось загрузить/i)
        .first(),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Upload failed|Ошибка загрузки/i).first()).toBeVisible();

    await page
      .getByLabel(/Alternative text|Альтернативный текст/i)
      .first()
      .fill("Broken upload");
    await page.getByRole("button", { name: /Save presentation|Сохранить представление/i }).click();
    await expect(
      page
        .getByText(
          /Finish or fix each upload|Завершите или исправьте|component media upload failed|Could not upload|Не удалось загрузить/i,
        )
        .first(),
    ).toBeVisible();
    await expect(page.getByText(/Presentation saved|Представление сохранено/i)).toHaveCount(0);

    await page.getByRole("button", { name: /Retry upload|Повторить загрузку/i }).click();
    await expect(
      page.getByText(/File uploaded and ready|Файл загружен и готов/i).first(),
    ).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: /Save presentation|Сохранить представление/i }).click();
    await expect(page.getByText(/Presentation saved|Представление сохранено/i).first()).toBeVisible(
      { timeout: 15_000 },
    );
  });

  test("keeps keyboard focus order through source controls and save", async ({ page }) => {
    await page.goto(`/en/objects/component/${FIXTURE_COMPONENT_ID}/edit`);
    await page.locator("#presentation-bio").focus();
    await expect(page.locator("#presentation-bio")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      page.getByRole("button", { name: /Save presentation|Сохранить представление/i }),
    ).toBeVisible();
    await expect(page.getByText(/JPEG, PNG, WebP, GIF, MP4 or WebM/i)).toBeVisible();
  });
});
