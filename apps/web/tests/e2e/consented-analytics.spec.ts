import { expect, test } from "@playwright/test";

// The e2e server runs with test measurement ids (playwright.config.ts). Vendor
// requests are answered locally, so the test needs no outside network.
const vendor =
  /^https:\/\/(www\.googletagmanager\.com|www\.google-analytics\.com|mc\.yandex\.(ru|com))\//;

test("analytics load only after consent and leave after withdrawal", async ({ page, context }) => {
  await context.clearCookies();
  const requested: string[] = [];
  await page.route(vendor, async (route) => {
    requested.push(new URL(route.request().url()).host);
    await route.fulfill({ status: 200, contentType: "text/javascript", body: "" });
  });

  await page.goto("/en/catalog");
  const choices = page.getByRole("dialog", { name: "Cookie choices" });
  await expect(choices).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(requested).toEqual([]);

  await choices.getByRole("button", { name: "Accept all" }).click();
  await expect
    .poll(() => [...new Set(requested)].sort())
    .toEqual(["mc.yandex.ru", "www.googletagmanager.com"]);
  await expect(page.locator('script[src="https://mc.yandex.ru/metrika/tag.js"]')).toHaveCount(1);

  // Stand in for the cookies the vendors set on the site's own host.
  const url = new URL(page.url());
  await context.addCookies(
    ["_ga", "_ym_uid"].map((name) => ({ name, value: "1", domain: url.hostname, path: "/" })),
  );

  await page.getByRole("button", { name: "Cookie settings" }).first().click();
  await choices.getByRole("checkbox", { name: "Analytics" }).uncheck();
  await choices.getByRole("button", { name: "Save choices" }).click();

  await expect(page.locator('script[src="https://mc.yandex.ru/metrika/tag.js"]')).toHaveCount(0);
  const names = (await context.cookies()).map((cookie) => cookie.name);
  expect(names).not.toContain("_ga");
  expect(names).not.toContain("_ym_uid");
  expect(names).toContain("ai_stp_consent");

  const afterWithdrawal = requested.length;
  await page.reload();
  await page.waitForLoadState("networkidle");
  expect(requested).toHaveLength(afterWithdrawal);
});
