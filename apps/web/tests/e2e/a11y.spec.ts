import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { A11Y_BUDGETS } from "../../src/lib/budgets";

/**
 * REQ-2213: axe critical and serious counts stay within A11Y_BUDGETS.
 */
const ROUTES = ["/en", "/en/catalog", "/en/login", "/en/account", "/en/devices"] as const;

test.describe("accessibility budgets (REQ-2213)", () => {
  for (const route of ROUTES) {
    test(`axe critical/serious = 0 on ${route}`, async ({ page }) => {
      if (route === "/en/account" || route === "/en/devices") {
        await page.goto("/en/login");
        await page
          .getByRole("button", {
            name: /Continue with GitHub|\u0412\u043e\u0439\u0442\u0438 \u0447\u0435\u0440\u0435\u0437 GitHub/i,
          })
          .click();
        await expect(page).toHaveURL(/\/en\/account/);
      }
      await page.goto(route);
      // Protected routes redirect when session is missing; after login they load.
      if (route === "/en/devices") {
        await expect(page.getByRole("heading", { name: "fixture-device" })).toBeVisible({
          timeout: 15_000,
        });
      } else if (route === "/en/account") {
        await expect(page.getByText(/account_01JQZK7B8N4M6P2R9T5V0X3Y7Z/)).toBeVisible({
          timeout: 15_000,
        });
      } else {
        await expect(page.locator("body")).toBeVisible();
      }

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();

      const critical = results.violations.filter((v) => v.impact === "critical");
      const serious = results.violations.filter((v) => v.impact === "serious");

      expect(
        critical.length,
        critical.map((v) => v.id).join(", ") || "critical",
      ).toBeLessThanOrEqual(A11Y_BUDGETS.axeCritical);
      expect(serious.length, serious.map((v) => v.id).join(", ") || "serious").toBeLessThanOrEqual(
        A11Y_BUDGETS.axeSerious,
      );
    });
  }
});
