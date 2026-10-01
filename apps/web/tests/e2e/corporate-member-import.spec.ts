import path from "node:path";
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("file picker, drop, preview validation, localized help and main navigation", async ({
  page,
}, info) => {
  test.skip(
    process.env["AI_STP_CORPORATE_E2E"] !== "offline",
    "Uses disposable corporate fixtures",
  );
  test.setTimeout(180_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const root = "/en/corporate/organization/admins";
  await page.goto(`/en/login?returnTo=${encodeURIComponent(root)}`);
  await page.getByRole("button", { name: /Continue with GitHub/ }).click();
  await page.waitForURL(`**${root}`);
  const main = page.locator("#main-content");
  const table = main.getByRole("table");
  const role = table.locator('a[href*="/admins/roles?role="]').first();
  await expect(role).toHaveAttribute("href", /\/roles\?role=/);
  await expect(table.locator('a[href*="/corporate/teams/"]').first()).toBeVisible();
  const menuTrigger = table.getByRole("button", { name: /Actions for/ }).first();
  await menuTrigger.click();
  await expect(page.locator("body")).not.toHaveAttribute("data-scroll-locked");
  const before = await page.evaluate(() => scrollY);
  await page.mouse.wheel(0, 350);
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(before);
  await page.keyboard.press("Escape");
  await main.getByRole("link", { name: "Invitations", exact: true }).click();
  await main.getByRole("button", { name: "Invite member", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "File import help" }).click();
  const help = page.getByRole("dialog", { name: "File import help" });
  await expect(help).toContainText("email,display_name");
  await page.keyboard.press("Escape");
  await page.getByRole("dialog").getByRole("button", { name: "Import from file" }).click();
  const dialog = page.getByRole("dialog", { name: "Import from file", exact: true });
  const picker = page.waitForEvent("filechooser");
  await dialog.locator('label[for="import-file"]').click();
  await (await picker).setFiles(path.resolve("tests/fixtures/member-import.xlsx"));
  await expect(dialog.getByRole("table")).toContainText("Spreadsheet Member");
  const input = dialog.locator('input[type="file"]');
  for (const [name, text, expected] of [
    ["people.json", '[{"email":"json@example.com","display_name":"JSON Member"}]', "JSON Member"],
    [
      "people.md",
      "| email | display_name |\n| --- | --- |\n| md@example.com | Markdown Member |",
      "Markdown Member",
    ],
    ["people.txt", "Text Member <txt@example.com>", "Text Member"],
  ]) {
    await input.setInputFiles({
      name: name ?? "",
      mimeType: "text/plain",
      buffer: Buffer.from(text ?? ""),
    });
    await expect(dialog.getByRole("table")).toContainText(expected ?? "");
  }
  const transfer = await page.evaluateHandle(() => {
    const data = new DataTransfer();
    data.items.add(
      new File(
        [
          'email,role,display_name\nalex@example.com,lead,"Morgan, Alex"\nalex@example.com,staff,Duplicate\nbad,staff,Invalid',
        ],
        "people.csv",
        { type: "text/csv" },
      ),
    );
    return data;
  });
  await dialog
    .locator('label[for="import-file"]')
    .dispatchEvent("drop", { dataTransfer: transfer });
  await expect(dialog.getByRole("table")).toContainText("Morgan, Alex");
  await expect(dialog.getByRole("table")).not.toContainText("lead,Morgan");
  await expect(dialog.getByText("Duplicate email", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Invalid email", { exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual(
    [],
  );
  await page.screenshot({
    path: path.resolve(`../../.impeccable/review/import-${info.project.name}.png`),
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.keyboard.press("Escape");
  await page.goto("/ru/corporate/organization/admins?tab=invitations");
  await main.getByRole("button", { name: "Пригласить участника", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Справка по импорту" }).click();
  await expect(page.getByRole("dialog", { name: "Справка по импорту" })).toContainText(
    "В CSV и XLSX",
  );
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  await page.goto("/en/corporate/organization/admins/employees");
  if (info.project.name.includes("mobile"))
    await page.getByRole("button", { name: "Open menu", exact: true }).click();
  const nav = info.project.name.includes("mobile")
    ? page.getByRole("dialog", { name: "Primary navigation" })
    : page.locator('[data-ui="context-sidebar"]');
  await nav.getByRole("button", { name: "Main navigation", exact: true }).click();
  await expect(page).toHaveURL(/\/admins\/employees$/);
  await expect(nav.getByRole("link", { name: "Overview", exact: true })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Catalog", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("recipient preview Storybook states remain accessible at mobile width", async ({ page }) => {
  const url = process.env["AI_STP_STORYBOOK_URL"];
  test.skip(!url, "Uses built Storybook");
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 390, height: 800 });
  for (const story of [
    "ready",
    "empty",
    "loading",
    "invalid",
    "long-values",
    "dark",
    "russian",
    "mobile",
  ]) {
    await page.goto(
      `${url}/iframe.html?id=ui-kit-molecules-memberimportpreview--${story}&viewMode=story`,
    );
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.locator("html")).toHaveClass(story === "dark" ? /dark/ : /^(?!.*dark)/);
    // Theme globals apply after rendering; check contrast after color transitions settle.
    await expect
      .poll(() =>
        page.evaluate(() =>
          document
            .getAnimations()
            .every(
              (animation) =>
                !(animation instanceof CSSTransition) || animation.playState !== "running",
            ),
        ),
      )
      .toBe(true);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      story,
    ).toBe(true);
    expect(
      (await new AxeBuilder({ page }).include("#storybook-root").analyze()).violations,
      story,
    ).toEqual([]);
  }
});

test("invitation role availability stays visible and localized in Storybook", async ({ page }) => {
  const url = process.env["AI_STP_STORYBOOK_URL"];
  test.skip(!url, "Uses built Storybook");
  test.setTimeout(120_000);
  for (const story of [
    "invite-restricted",
    "invite-no-authority",
    "invite-roles-unavailable",
    "invite-restricted-russian",
  ]) {
    await page.goto(
      `${url}/iframe.html?id=ui-kit-organisms-corporatepeople--${story}&viewMode=story`,
    );
    const russian = story.endsWith("russian");
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(page.locator("html")).toHaveClass(russian ? /dark/ : /^(?!.*dark)/);
    const select = dialog.getByRole("combobox", { name: russian ? "Роль" : "Role", exact: true });
    const suffix = russian ? "недоступна" : "unavailable";
    await expect(select.getByRole("option", { name: `staff — ${suffix}` })).toBeDisabled();
    await expect(select.getByRole("option", { name: `lead — ${suffix}` })).toBeDisabled();
    if (story.includes("restricted")) {
      await expect(select.getByRole("option", { name: "superadmin", exact: true })).toBeEnabled();
      await expect(select).toHaveAccessibleDescription(
        russian ? /права, которые вы не можете назначать/ : /permissions you cannot grant/,
      );
      await select.selectOption("superadmin");
      await dialog
        .getByRole("button", {
          name: russian ? "Импорт из файла" : "Import from file",
          exact: true,
        })
        .click();
      await expect(select).toHaveValue("superadmin");
    } else {
      await expect(dialog.getByRole("alert")).toContainText(
        story === "invite-roles-unavailable" ? "Could not verify" : "No roles are available",
      );
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await expect
      .poll(() =>
        page.evaluate(() =>
          document
            .getAnimations()
            .every(
              (animation) =>
                !(animation instanceof CSSTransition) || animation.playState !== "running",
            ),
        ),
      )
      .toBe(true);
    expect(
      (await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations,
    ).toEqual([]);
  }
});
