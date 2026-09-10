import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const VIEWPORTS = [
  { width: 360, height: 800 },
  { width: 430, height: 932 },
  { width: 768, height: 1024 },
  { width: 1280, height: 900 },
] as const;
const LOCALES = ["en", "ru"] as const;
const MODES = ["local", "personal", "corporate"] as const;
const STATES = {
  empty: "No organizations",
  partial: "Context partially loaded",
  forbidden: "Access denied",
  unavailable: "Context unavailable",
  stale: "Context is stale",
  failed: "Context failed",
  unauthenticated: "Sign-in required",
} as const;
const profile = process.env["AI_STP_WEB_PROFILE"] ?? "public_saas";

async function fixture(page: Page, mode: string, authenticated = true) {
  if (authenticated) {
    await page.goto("/en/login");
    await page.getByRole("button", { name: "Continue with GitHub" }).click();
    await expect(page).toHaveURL(/\/en\/account/);
  }
  await page.context().addCookies([
    {
      name: "ai_stp_context_fixture",
      value: mode,
      domain: "127.0.0.1",
      path: "/",
    },
    ...(mode === "local"
      ? [
          {
            name: "ai_stp_product_mode",
            value: "local",
            domain: "127.0.0.1",
            path: "/",
          },
        ]
      : []),
  ]);
}

test.describe(`shared context matrix / ${profile} (REQ-7712)`, () => {
  for (const mode of MODES) {
    for (const locale of LOCALES) {
      for (const viewport of VIEWPORTS) {
        test(`${mode} ${locale} ${viewport.width}px keyboard/a11y`, async ({ page }) => {
          await page.setViewportSize(viewport);
          await page.emulateMedia({ reducedMotion: "reduce" });
          await fixture(page, mode, mode !== "local");
          await page.goto(`/${locale}/workspace`);
          const select = page.getByRole("combobox").first();
          await select.focus();
          await expect(select).toBeFocused();
          await expect(page.locator('[data-ui="context-workspace"]')).toBeVisible();
          await expect(
            page.getByRole("link", { name: locale === "en" ? "Projects" : "Проекты", exact: true }),
          ).toBeVisible();
          const width = await page.evaluate(() => ({
            scroll: document.documentElement.scrollWidth,
            client: document.documentElement.clientWidth,
          }));
          expect(width.scroll).toBeLessThanOrEqual(width.client);
          const results = await new AxeBuilder({ page })
            .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
            .analyze();
          expect(
            results.violations.filter((item) =>
              ["critical", "serious"].includes(item.impact ?? ""),
            ),
          ).toEqual([]);
        });
      }
    }
  }

  for (const mode of MODES) {
    for (const authenticated of [false, true]) {
      test(`direct ${mode} URL / authenticated=${authenticated}`, async ({ page }) => {
        await fixture(page, mode, authenticated);
        await page.goto("/en/workspace?surface=projects");
        const workspace = page.locator('[data-ui="context-workspace"]');
        if (mode !== "local" && !authenticated) {
          await expect(workspace).toContainText(STATES.unauthenticated);
          await expect(page.getByRole("link", { name: "Projects", exact: true })).toHaveCount(0);
        } else {
          await expect(workspace.locator("header p").first()).toHaveText(mode, {
            ignoreCase: true,
          });
          await expect(page.getByRole("link", { name: "Projects", exact: true })).toBeVisible();
        }
      });
    }
  }

  for (const [state, label] of Object.entries(STATES)) {
    test(`${state} is distinct on direct URL`, async ({ page }) => {
      await fixture(page, state);
      await page.goto("/en/workspace");
      await expect(page.locator('[data-ui="context-workspace"]')).toContainText(label);
      await expect(page.getByRole("link", { name: "Projects", exact: true })).toHaveCount(0);
    });
  }

  test("denied capability and expired projection fail closed", async ({ page }) => {
    await fixture(page, "corporate-denied");
    await page.goto("/en/workspace?surface=projects");
    await expect(page.locator('[data-ui="context-workspace"]')).toContainText("Access denied");
    await expect(page.getByRole("link", { name: "Projects", exact: true })).toHaveCount(0);
    await page.context().addCookies([
      {
        name: "ai_stp_context_fixture",
        value: "corporate-expired",
        domain: "127.0.0.1",
        path: "/",
      },
    ]);
    await page.reload();
    await expect(page.locator('[data-ui="context-workspace"]')).toContainText("Context is stale");
    await expect(page.getByRole("link", { name: "Projects", exact: true })).toHaveCount(0);
  });

  test("future corporate owners are unavailable, including direct URLs", async ({ page }) => {
    await fixture(page, "corporate");
    await page.goto("/en/workspace");
    await expect(page.locator('[data-ui="unavailable-surface"]')).toHaveCount(4);
    for (const surface of ["teams", "assignments", "audit", "saml"]) {
      await page.goto(`/en/workspace?surface=${surface}`);
      const workspace = page.locator('[data-ui="context-workspace"]');
      await expect(workspace).toContainText("Not supported");
      await expect(workspace.getByRole("button")).toHaveCount(0);
      await expect(workspace.getByRole("link")).toHaveCount(0);
    }
  });

  test("personal mode rejects corporate-only direct URLs", async ({ page }) => {
    await fixture(page, "personal");
    await page.goto("/en/workspace?surface=teams");
    const workspace = page.locator('[data-ui="context-workspace"]');
    await expect(workspace).toContainText("Not supported");
    await expect(workspace.getByRole("link")).toHaveCount(0);
  });

  test("switch discards an old corporate response released after local navigation", async ({
    page,
  }) => {
    await fixture(page, "corporate");
    await page.goto("/en/workspace");
    await expect(page.locator('[data-ui="context-organization"]')).toHaveText("Acme Corp");
    let release = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    let captured = () => {};
    const capturedResponse = new Promise<void>((resolve) => {
      captured = resolve;
    });
    let delivered = () => {};
    const deliveredResponse = new Promise<void>((resolve) => {
      delivered = resolve;
    });
    await page.route("**/en/workspace*", async (route) => {
      if (
        !route.request().headers()["rsc"] ||
        !route.request().url().includes("surface=projects")
      ) {
        return route.continue();
      }
      const response = await route.fetch();
      captured();
      await held;
      await route.fulfill({ response }).catch(() => {});
      delivered();
    });
    const oldNavigation = page
      .getByRole("link", { name: "Projects", exact: true })
      .evaluate((link) => {
        (link as HTMLAnchorElement).click();
      });
    await capturedResponse;
    await page.getByRole("combobox").first().selectOption("local");
    await page.waitForURL(
      (url) => url.pathname === "/en/workspace" && !url.searchParams.has("surface"),
    );
    release();
    await oldNavigation.catch(() => {});
    await deliveredResponse;
    const workspace = page.locator('[data-ui="context-workspace"]');
    await expect(workspace.locator("header p").first()).toHaveText("Local");
    await expect(workspace).not.toContainText("Acme Corp");
    await expect(workspace.locator("header p").first()).toHaveText("Local");
    await expect(page.getByRole("combobox").first()).toHaveValue("local");
  });
});
