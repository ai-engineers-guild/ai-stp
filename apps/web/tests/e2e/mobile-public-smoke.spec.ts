import { mkdir } from "node:fs/promises";
import path from "node:path";

import { expect, type Locator, type Page, test } from "@playwright/test";

const VIEWPORTS = [
  { width: 360, height: 800 },
  { width: 430, height: 932 },
] as const;
const LOCALES = ["en", "ru"] as const;
const COMPONENT_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YBE";
const SETUP_ID = "setup_01JQZK7B8N4M6P2R9T5V0X3YC2";
const ACCOUNT_ID = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z";

// Same default as scripts/verify-production.mjs and shell-machine-contact.spec.ts.
const reviewDir = path.resolve(
  process.cwd(),
  process.env.VERIFY_REVIEW_DIR ?? "test-results/review",
);

test.beforeAll(async () => {
  await mkdir(reviewDir, { recursive: true });
});

async function assertNoDocumentOverflow(page: Page) {
  const size = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(size.scroll).toBeLessThanOrEqual(size.client);
}

async function assertDismissAndReturnFocus(page: Page, trigger: Locator, surface: Locator) {
  await page.keyboard.press("Escape");
  await expect(surface).toBeHidden();
  await expect(trigger).toBeFocused();
}

async function assertInstallCta(page: Page) {
  const heading = page.getByRole("heading", { name: /Use via CLI|Использовать через CLI/ });
  await expect(heading).toBeVisible();
  const panel = heading.locator("xpath=ancestor::section[1]");
  await expect(panel.locator("code")).toBeVisible();
  await expect(panel.getByRole("button", { name: /Copy|Копировать/ })).toBeVisible();
}

async function assertViewSourceCta(page: Page) {
  await expect(
    page.getByRole("link", { name: /View source on GitHub|Исходный код на GitHub/ }),
  ).toBeVisible();
}

async function assertMobileNavKeyboardAndBackdrop(page: Page, width: number) {
  const trigger = page.getByRole("button", { name: /Open menu|Открыть меню/ });
  await expect(trigger).toBeVisible();
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: /Primary navigation|Основная навигация/ });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("link").first()).toBeVisible();
  await assertDismissAndReturnFocus(page, trigger, dialog);

  await trigger.click();
  await expect(dialog).toBeVisible();
  // `toBeVisible` resolves the moment the dialog is in the DOM and painted, which
  // is earlier than this click can be seen. The surface animates in over
  // `--duration-normal`, and Radix attaches its outside-pointerdown listener in an
  // effect after mount; a raw `mouse.click` fired in that window lands on nothing
  // and the dialog stays open. It failed on `en` at 360 in one run and on `ru` at
  // 360 and 430 in the next, which is the signature of a race rather than a layout.
  //
  // A trial click runs the actionability checks and performs no action: it waits
  // for the same bounding box across two animation frames, so it returns only once
  // the entry animation has settled and the effect has certainly run.
  await dialog.getByRole("link").first().click({ trial: true });
  await page.mouse.click(width - 8, 80);
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
}

async function assertRefinementKeyboardAndBackdrop(page: Page) {
  const trigger = page.locator('[data-ui="catalog-filters"]');
  await expect(trigger).toBeVisible();
  await trigger.click();
  const surface = page.getByRole("dialog", { name: /Filters|Фильтры/ });
  await expect(surface).toBeVisible();
  await expect(surface).toContainText(/Apply|Применить|Reset|Сбросить/);
  await assertDismissAndReturnFocus(page, trigger, surface);

  await trigger.click();
  await expect(surface).toBeVisible();
  await page.locator("button.fixed.inset-0").click({ force: true, position: { x: 8, y: 8 } });
  await expect(surface).toBeHidden();
  await expect(trigger).toBeFocused();
}

async function assertAccountDrawerKeyboardAndBackdrop(page: Page) {
  const trigger = page.locator('[data-ui="nav-account"]');
  await expect(trigger).toBeVisible();
  await trigger.click();
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("menuitem").first()).toBeVisible();
  await assertDismissAndReturnFocus(page, trigger, menu);
  // Account is an anchored menu with no modal backdrop (t1). Pointer-outside
  // dismiss is not a stable public fixture on 360-430; Escape owns close/focus.
}

test.describe("mobile public smoke (issue 266)", () => {
  for (const viewport of VIEWPORTS) {
    for (const locale of LOCALES) {
      test(`${locale} ${viewport.width}px landing, catalog, detail, login, account`, async ({
        page,
      }, testInfo) => {
        test.skip(testInfo.project.name !== "chromium", "explicit 360/430 viewports");
        await page.setViewportSize(viewport);

        await page.goto(`/${locale}`);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await expect(
          page.getByRole("link", { name: /Browse catalog|Открыть каталог/ }),
        ).toBeVisible();
        await expect(page.getByRole("heading", { name: /Install|Установка/ })).toBeVisible();
        await assertNoDocumentOverflow(page);
        await assertMobileNavKeyboardAndBackdrop(page, viewport.width);
        await page.screenshot({
          path: path.join(reviewDir, `mobile-public-${locale}-${String(viewport.width)}.png`),
          fullPage: true,
        });

        await page.goto(`/${locale}/catalog`);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await assertNoDocumentOverflow(page);
        await assertRefinementKeyboardAndBackdrop(page);
        await expect(page.locator("article[data-kind='component']").first()).toBeVisible({
          timeout: 15_000,
        });

        await page.goto(`/${locale}/catalog/components/${COMPONENT_ID}`);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await assertInstallCta(page);
        await assertViewSourceCta(page);
        await assertNoDocumentOverflow(page);

        await page.goto(`/${locale}/catalog/setups/${SETUP_ID}`);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await assertInstallCta(page);
        await assertNoDocumentOverflow(page);

        await page.goto(`/${locale}/login`);
        const github = page.getByRole("button", {
          name: /Continue with GitHub|Войти через GitHub/,
        });
        await expect(github).toBeVisible();
        await assertNoDocumentOverflow(page);
        await github.click();
        await expect(page).toHaveURL(new RegExp(`/${locale}/account`));
        await expect(page.getByText(ACCOUNT_ID)).toBeVisible();
        await assertNoDocumentOverflow(page);
        await assertAccountDrawerKeyboardAndBackdrop(page);
      });
    }
  }
});
