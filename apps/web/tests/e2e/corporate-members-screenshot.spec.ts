import path from "node:path";
import { mkdir, readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("member administration filters, selection export, invite and bulk history", async ({
  page,
}, info) => {
  test.skip(
    process.env["AI_STP_CORPORATE_E2E"] !== "offline",
    "Uses disposable mock members and invitations",
  );
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`${message.text()} ${message.location().url}`);
  });
  const root = "/en/corporate/organization/admins";
  const favicon = await page.request.get("/favicon.ico");
  expect(favicon.status()).toBe(200);
  expect(favicon.headers()["content-type"]).toContain("image/png");
  await page.goto(`/en/login?returnTo=${encodeURIComponent(root)}`);
  await page.getByRole("button", { name: /Continue with GitHub/ }).click();
  await expect(page).toHaveURL(new RegExp(`${root}$`));
  await page.setViewportSize({ width: 1672, height: 940 });
  const main = page.locator("#main-content");
  const dir = path.resolve(process.cwd(), "../../.impeccable/review");
  await mkdir(dir, { recursive: true });
  await page.locator('[data-ui="site-header"]').getByRole("button", { name: /theme/i }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  const primary = await main
    .getByRole("button", { name: "Add member", exact: true })
    .evaluate((node) => getComputedStyle(node).backgroundColor);
  await expect(main.getByRole("link", { name: "Members", exact: true })).toHaveCSS(
    "border-bottom-color",
    primary,
  );
  await page.screenshot({ path: path.join(dir, `members-reference-${info.project.name}.png`) });
  await main.getByRole("button", { name: "Page 2", exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await main.getByRole("searchbox").fill("member1@corp.example");
  await expect(main.locator("tbody tr")).toHaveCount(1);
  await expect(page).not.toHaveURL(/page=2/);
  await main.getByRole("checkbox", { name: "Select all rows on this page" }).check();
  await main.getByRole("button", { name: "Directory actions" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("menuitem", { name: "Download CSV" }).click();
  const file = await (await download).path();
  expect(file).not.toBeNull();
  if (!file) throw new Error("The CSV download was not saved");
  const csv = await readFile(file, "utf8");
  expect(csv).toContain("member1@corp.example");
  expect(csv).not.toContain("#token");
  await main.getByRole("searchbox").clear();
  await main.getByRole("button", { name: "Clear selection", exact: true }).click();
  await main.getByRole("link", { name: "Invitations", exact: true }).click();
  await main.getByRole("button", { name: "Invite member", exact: true }).click();
  let dialog = page.getByRole("dialog", { name: "Invite member", exact: true });
  await expect(dialog.locator("#invite-email")).toBeFocused();
  await page.screenshot({ path: path.join(dir, `invite-reference-${info.project.name}.png`) });
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual(
    [],
  );
  const email = `screenshot-${info.project.name}@example.com`;
  await dialog.locator("#invite-email").fill(email);
  await dialog.locator("#invite-role").selectOption("staff");
  await dialog.locator("#invite-ttl").selectOption("14");
  await dialog.locator("summary").click();
  await dialog.getByRole("checkbox").first().check();
  await dialog.getByRole("button", { name: "Send invitation", exact: true }).click();
  const receipt = page.getByRole("dialog", { name: "Invitations sent", exact: true });
  await expect(receipt.getByText(email)).toBeVisible();
  await receipt.getByRole("button", { name: "Close", exact: true }).click();
  const row = main.getByRole("row").filter({ hasText: email });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: /Actions for/ }).click();
  await page.getByRole("menuitem", { name: "Revoke invitation", exact: true }).click();
  await page
    .getByRole("dialog", { name: "Revoke invitation", exact: true })
    .getByRole("button", { name: "Revoke invitation", exact: true })
    .click();
  await expect(row).toHaveCount(0);
  await main.getByRole("combobox", { name: "All statuses" }).selectOption("revoked");
  await expect(row).toContainText("Revoked");
  await main.getByRole("button", { name: "Invite member", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Import from file" }).click();
  dialog = page.getByRole("dialog", { name: "Import from file", exact: true });
  await dialog.locator("summary").filter({ hasText: "Or paste a list" }).click();
  await dialog
    .locator("#import-text")
    .fill(
      `display_name,email\nBulk One,bulk-one-${info.project.name}@example.com\nBulk Two,bulk-two-${info.project.name}@example.com`,
    );
  await dialog.locator("#invite-role").selectOption("staff");
  await dialog.getByRole("button", { name: "Send invitations", exact: true }).click();
  await expect(receipt.getByText(/bulk-one-/)).toBeVisible();
  await expect(receipt.getByText(/bulk-two-/)).toBeVisible();
  await receipt.getByRole("button", { name: "Close", exact: true }).click();
  await main.getByRole("combobox", { name: "All statuses" }).selectOption("pending");
  await expect(main.getByText(`bulk-one-${info.project.name}@example.com`)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 800 });
  await page.screenshot({
    path: path.join(dir, `members-mobile-reference-${info.project.name}.png`),
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await main.getByRole("button", { name: "Invite member", exact: true }).click();
  await page.screenshot({
    path: path.join(dir, `invite-mobile-reference-${info.project.name}.png`),
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(main.getByRole("button", { name: "Invite member", exact: true })).toBeFocused();
  await page.goto("/ru/corporate/organization/admins");
  await expect(
    page.getByRole("heading", { name: "Участники и приглашения", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#locale-select")).toHaveText("en");
  await expect(page.locator("#main-content tbody")).toContainText(/назад|вчера|сегодня/);
  await expect(page.locator("#main-content tbody")).not.toContainText(/ago|this minute/);
  expect(errors).toEqual([]);
});

test("Storybook member administration states are accessible and responsive", async ({ page }) => {
  test.setTimeout(180_000);
  const url = process.env["AI_STP_STORYBOOK_URL"];
  test.skip(!url, "Uses the built Storybook when AI_STP_STORYBOOK_URL is set");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const story of [
    "members",
    "dark",
    "empty",
    "read-only",
    "mobile",
    "invitations",
    "unavailable",
    "invite",
    "invite-error",
    "invite-busy",
    "bulk-import",
    "table",
    "table-empty",
    "table-selected",
    "table-mobile",
  ]) {
    await page.setViewportSize({ width: story === "mobile" ? 390 : 1440, height: 900 });
    await page.goto(
      `${url}/iframe.html?id=ui-kit-organisms-corporatepeople--${story}&viewMode=story`,
    );
    await expect(page.locator("html")).toHaveClass(story === "dark" ? /dark/ : /^(?!.*dark)/);
    const foreground = await page.locator("body").evaluate((node) => getComputedStyle(node).color);
    await expect(page.locator("#storybook-root .min-h-dvh").first()).toHaveCSS("color", foreground);
    const invite = story.startsWith("invite") || story === "bulk-import";
    if (invite) {
      await expect(page.getByRole("dialog")).toBeVisible();
      if (story === "invite-busy") await expect(page.locator("#invite-email")).toBeDisabled();
      if (story === "invite-error") await expect(page.getByRole("alert")).toBeVisible();
      if (story === "bulk-import")
        await expect(page.getByLabel("Click to choose a file")).toBeVisible();
    } else if (story === "unavailable") {
      await expect(page.getByRole("alert")).toHaveText(
        "Invitations could not be loaded. Reload the page to retry.",
      );
    } else {
      await expect(page.getByRole("table")).toBeVisible();
      if (story === "read-only")
        await expect(page.getByRole("button", { name: "Add member", exact: true })).toHaveCount(0);
    }
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      story,
    ).toBe(true);
    expect(
      (
        await new AxeBuilder({ page })
          .include(invite ? '[role="dialog"]' : "#storybook-root")
          .analyze()
      ).violations,
      story,
    ).toEqual([]);
  }
  expect(errors).toEqual([]);
});
