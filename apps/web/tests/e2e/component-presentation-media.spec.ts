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
    await page
      .getByRole("button", {
        name: /Continue with GitHub|\u0412\u043e\u0439\u0442\u0438 \u0447\u0435\u0440\u0435\u0437 GitHub/i,
      })
      .click();
    await expect(page).toHaveURL(/\/en\/account/);
  });

  test("uploads image media, shows preview, and saves presentation", async ({ page }) => {
    await page.goto(`/en/objects/component/${FIXTURE_COMPONENT_ID}/edit`);
    await expect(
      page.getByRole("heading", {
        name: /Edit bio and media|\u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0431\u0438\u043e \u0438 \u043c\u0435\u0434\u0438\u0430/i,
      }),
    ).toBeVisible();
    await expect(page.getByText(/JPEG, PNG, WebP, GIF, MP4 or WebM/i)).toBeVisible();

    await selectUploadSource(page);
    await page.locator('input[type="file"]').first().setInputFiles("public/brand/icon-32.png");
    await expect(page.locator("img[src^='data:image']").first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page
        .getByText(
          /File uploaded and ready|\u0424\u0430\u0439\u043b \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d \u0438 \u0433\u043e\u0442\u043e\u0432/i,
        )
        .first(),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('input[value*="/v1/media/component/"]')).toHaveCount(0);

    await page
      .getByLabel(
        /Alternative text|\u0410\u043b\u044c\u0442\u0435\u0440\u043d\u0430\u0442\u0438\u0432\u043d\u044b\u0439 \u0442\u0435\u043a\u0441\u0442/i,
      )
      .first()
      .fill("E2E uploaded cover");
    await page.locator("#presentation-bio").fill("E2E presentation bio with uploaded media");

    await page
      .getByRole("button", {
        name: /Save presentation|\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043f\u0440\u0435\u0434\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0438\u0435/i,
      })
      .click();
    await expect(
      page
        .getByText(
          /Presentation saved|\u041f\u0440\u0435\u0434\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e/i,
        )
        .first(),
    ).toBeVisible({ timeout: 15_000 });

    await page.reload();
    await expect(page.locator("#presentation-bio")).toHaveValue(
      "E2E presentation bio with uploaded media",
    );
    await expect(
      page
        .getByLabel(
          /Alternative text|\u0410\u043b\u044c\u0442\u0435\u0440\u043d\u0430\u0442\u0438\u0432\u043d\u044b\u0439 \u0442\u0435\u043a\u0441\u0442/i,
        )
        .first(),
    ).toHaveValue("E2E uploaded cover");
    await expect(
      page
        .getByText(
          /File uploaded and ready|\u0424\u0430\u0439\u043b \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d \u0438 \u0433\u043e\u0442\u043e\u0432|Ready|\u0413\u043e\u0442\u043e\u0432\u043e/i,
        )
        .first(),
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
      page
        .getByText(
          /Unsupported file type|\u041d\u0435\u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u043c\u044b\u0439 \u0442\u0438\u043f \u0444\u0430\u0439\u043b\u0430/i,
        )
        .first(),
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
        .getByText(
          /component media upload failed|Could not upload|\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c/i,
        )
        .first(),
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page
        .getByText(
          /Upload failed|\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438/i,
        )
        .first(),
    ).toBeVisible();

    await page
      .getByLabel(
        /Alternative text|\u0410\u043b\u044c\u0442\u0435\u0440\u043d\u0430\u0442\u0438\u0432\u043d\u044b\u0439 \u0442\u0435\u043a\u0441\u0442/i,
      )
      .first()
      .fill("Broken upload");
    await page
      .getByRole("button", {
        name: /Save presentation|\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043f\u0440\u0435\u0434\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0438\u0435/i,
      })
      .click();
    await expect(
      page
        .getByText(
          /Finish or fix each upload|\u0417\u0430\u0432\u0435\u0440\u0448\u0438\u0442\u0435 \u0438\u043b\u0438 \u0438\u0441\u043f\u0440\u0430\u0432\u044c\u0442\u0435|component media upload failed|Could not upload|\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c/i,
        )
        .first(),
    ).toBeVisible();
    await expect(
      page.getByText(
        /Presentation saved|\u041f\u0440\u0435\u0434\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e/i,
      ),
    ).toHaveCount(0);

    await page
      .getByRole("button", {
        name: /Retry upload|\u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0443/i,
      })
      .click();
    await expect(
      page
        .getByText(
          /File uploaded and ready|\u0424\u0430\u0439\u043b \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d \u0438 \u0433\u043e\u0442\u043e\u0432/i,
        )
        .first(),
    ).toBeVisible({ timeout: 15_000 });
    await page
      .getByRole("button", {
        name: /Save presentation|\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043f\u0440\u0435\u0434\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0438\u0435/i,
      })
      .click();
    await expect(
      page
        .getByText(
          /Presentation saved|\u041f\u0440\u0435\u0434\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e/i,
        )
        .first(),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("keeps keyboard focus order through source controls and save", async ({ page }) => {
    await page.goto(`/en/objects/component/${FIXTURE_COMPONENT_ID}/edit`);
    // Clicked rather than `.focus()`d, because `goto` resolves on `load` and
    // hydration runs after it. `.focus()` waits only for the node to be
    // attached, so it can land on a pre-hydration node that React then
    // replaces, and the focus goes with it. `.click()` waits for the element to
    // be stable and able to receive events, which is the hydration gate this
    // needs. Linux and Windows happened to be fast enough; macOS was not, and
    // reported `inactive` fourteen times before timing out.
    const bio = page.locator("#presentation-bio");
    await bio.click();
    await expect(bio).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      page.getByRole("button", {
        name: /Save presentation|\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043f\u0440\u0435\u0434\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0438\u0435/i,
      }),
    ).toBeVisible();
    await expect(page.getByText(/JPEG, PNG, WebP, GIF, MP4 or WebM/i)).toBeVisible();
  });
});
