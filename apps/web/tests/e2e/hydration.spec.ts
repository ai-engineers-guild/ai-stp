import { expect, test } from "@playwright/test";

const routes = [
  "/en",
  "/en/catalog",
  "/en/catalog?view=cards",
  "/en/catalog/components/component_01JQZK7B8N4M6P2R9T5V0X3YBD",
  "/en/catalog/setups/setup_01JQZK7B8N4M6P2R9T5V0X3YC2",
  "/en/publishers/account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  "/en/contact",
  "/en/docs",
  "/en/login",
  "/en/account",
  "/en/devices",
  "/en/objects",
  "/en/access",
  "/en/reports",
] as const;

test.describe("hydration", () => {
  test("first visit without a consent cookie hydrates the landing page", async ({
    page,
    context,
  }) => {
    const runtimeErrors: string[] = [];
    await context.clearCookies();
    page.on("console", (message) => {
      if (/hydration|hydrated|server rendered html.*match/i.test(message.text())) {
        runtimeErrors.push(message.text());
      }
    });
    page.on("pageerror", (error) => runtimeErrors.push(error.message));

    await page.goto("/en", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(runtimeErrors).toEqual([]);
  });

  for (const route of routes) {
    test(`${route} hydrates without React mismatches`, async ({ page }) => {
      const runtimeErrors: string[] = [];
      page.on("console", (message) => {
        const text = message.text();
        if (/hydration|hydrated|server rendered html.*match/i.test(text)) {
          runtimeErrors.push(`[console] ${text}`);
        }
      });
      page.on("pageerror", (error) => {
        runtimeErrors.push(`[pageerror] ${error.message}`);
      });

      await page.goto(route, { waitUntil: "domcontentloaded" });
      await expect(page.locator("body")).toBeVisible();
      await page.waitForTimeout(250);

      expect(runtimeErrors, `Runtime errors while hydrating ${route}`).toEqual([]);
    });
  }
});
