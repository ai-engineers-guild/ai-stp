import path from "node:path";
import { mkdir } from "node:fs/promises";
import { expect, test, type Page, type TestInfo } from "@playwright/test";

/**
 * People & Access screens (Members & Invitations, Access model, Roles,
 * Employee access, Security service principals). Offline relies on the
 * populated mock-corporate fixture; live expects an authenticated storage
 * state and a populated organization. Mutations run in offline mode only.
 * AI_STP_CORPORATE_E2E=offline|live opts in; absent means skipped.
 */
const mode = process.env["AI_STP_CORPORATE_E2E"];
const state = process.env["AI_STP_CORPORATE_STORAGE_STATE"];
const main = (page: Page) => page.locator("#main-content");
const adminsBase = "/en/corporate/organization/admins";
const peopleAccessRoutes = [
  adminsBase,
  `${adminsBase}/access`,
  `${adminsBase}/roles`,
  `${adminsBase}/settings`,
  `${adminsBase}/security`,
  `${adminsBase}/employees`,
] as const;
test.use({
  navigationTimeout: 60_000,
  ...(mode === "live" && state ? { storageState: state } : {}),
  trace: "off",
  video: "off",
});
// Dev-mode and standalone servers compile each route on first hit; the default
// 5s expect timeout reads as flake, not as a real defect.
const urlTimeout = 60_000;
// Dev servers abort in-flight RSC/fetch streams when the client navigates away
// ("Connection closed.") вЂ” environment noise, not a page defect.
const devNoise = (message: string) =>
  message === "Connection closed." ||
  message.includes("caret-color") ||
  message.includes("favicon");
const watchErrors = (page: Page, sink: string[]) => {
  page.on("pageerror", (error) => {
    if (!devNoise(error.message)) sink.push(error.message);
  });
};

async function authenticate(page: Page) {
  page.setDefaultNavigationTimeout(urlTimeout);
  if (mode === "live") {
    expect(
      Boolean(state),
      "Live corporate verification requires AI_STP_CORPORATE_STORAGE_STATE",
    ).toBe(true);
    const me = await page.request.get("/v1/auth/me");
    expect(me.status(), "Existing real API session must be valid").toBe(200);
    return;
  }
  await page.goto("/en/login?returnTo=%2Fen%2Fcorporate%2Faccount", {
    waitUntil: "domcontentloaded",
  });
  await page.getByRole("button", { name: /Continue with GitHub/i }).click();
  await page.waitForURL("**/en/corporate/account", { timeout: urlTimeout });
  const darkTheme = page.getByRole("button", { name: "Use dark theme", exact: true });
  if (await darkTheme.count()) await darkTheme.click();
}

async function screenshot(page: Page, info: TestInfo, name: string) {
  const directory = path.resolve(process.cwd(), "../../.impeccable/review");
  await mkdir(directory, { recursive: true });
  const file = path.join(directory, `people-access-${mode}-${info.project.name}-${name}.png`);
  await page.screenshot({
    path: file,
    fullPage: ![
      "mobile-navigation",
      "entity-drawer",
      "access-sections",
      "roles",
      "employee-access",
    ].includes(name),
  });
  await info.attach(name, { path: file, contentType: "image/png" });
}

async function fitsViewport(page: Page) {
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
}

test.describe("People & Access administration", () => {
  test.beforeEach(async ({ page }, info) => {
    await page.emulateMedia({ colorScheme: "dark" });
    if (info.project.name === "chromium") await page.setViewportSize({ width: 1920, height: 1080 });
  });
  test.skip(
    !mode,
    "Opt in with AI_STP_CORPORATE_E2E=offline or live; this skip is not corporate verification",
  );

  test("anonymous visitors are redirected to corporate login on every screen", async ({
    browser,
    baseURL,
  }) => {
    test.setTimeout(180_000);
    const context = await browser.newContext({
      ...(baseURL ? { baseURL } : {}),
      storageState: { cookies: [], origins: [] },
    });
    const page = await context.newPage();
    try {
      for (const route of peopleAccessRoutes) {
        await page.goto(route, { waitUntil: "domcontentloaded" });
        await page.waitForURL(/\/en\/corporate\/login\?returnTo=/, { timeout: urlTimeout });
        expect(decodeURIComponent(new URL(page.url()).searchParams.get("returnTo") ?? "")).toBe(
          route,
        );
      }
    } finally {
      await context.close();
    }
  });

  test("members directory filters, invitations create, and tabs are URL-backed", async ({
    page,
  }, info) => {
    test.setTimeout(180_000);
    page.setDefaultTimeout(30_000);
    const pageErrors: string[] = [];
    watchErrors(page, pageErrors);
    await authenticate(page);
    await page.goto(adminsBase);
    await expect(
      main(page).getByRole("heading", { level: 1, name: "Members & Invitations" }),
    ).toBeVisible();
    await screenshot(page, info, "members");
    const membersTab = main(page).getByRole("link", { name: "Members" });
    const invitationsTab = main(page).getByRole("link", { name: "Invitations" });
    await expect(membersTab).toBeVisible();
    await expect(invitationsTab).toBeVisible();
    const search = main(page).locator('input[name="query"]').first();
    await search.fill("member1@corp.example");
    await expect(page).toHaveURL(/query=member1/, { timeout: urlTimeout });
    await expect(main(page).getByRole("cell").first()).toBeVisible();
    await expect(main(page).getByRole("row")).toHaveCount(2);
    await search.clear();
    await expect(main(page).getByRole("row")).toHaveCount(11);
    await invitationsTab.click();
    await expect(page).toHaveURL(/tab=invitations/, { timeout: urlTimeout });
    await main(page).getByRole("button", { name: "Invite member", exact: true }).click();
    await expect(page.getByRole("dialog").locator("#invite-email")).toBeVisible();
    await screenshot(page, info, "invitations");
    expect(pageErrors, "Browser runtime errors are failures").toEqual([]);
  });

  test("offline invitation issuance produces a link and an outstanding row", async ({ page }) => {
    test.setTimeout(180_000);
    page.setDefaultTimeout(30_000);
    test.skip(mode !== "offline", "Invitation mutation uses the offline fixture");
    await authenticate(page);
    await page.goto(`${adminsBase}?tab=invitations`);
    const email = `e2e-${Date.now()}@example.com`;
    await main(page).getByRole("button", { name: "Invite member", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Invite member", exact: true });
    await dialog.locator("#invite-email").fill(email);
    await dialog.locator("#invite-display-name").fill("E2E Invitee");
    await dialog.locator("#invite-role").selectOption("staff");
    await dialog.getByRole("button", { name: "Send invitation", exact: true }).click();
    const receipt = page.getByRole("dialog", { name: "Invitations sent", exact: true });
    await expect(receipt.getByText(email)).toBeVisible({ timeout: urlTimeout });
    await receipt.getByRole("button", { name: "Close", exact: true }).click();
    await expect(main(page).getByText(email)).toBeVisible({ timeout: urlTimeout });
  });

  test("access model exposes entities and matrix views", async ({ page }, info) => {
    test.setTimeout(180_000);
    page.setDefaultTimeout(30_000);
    const pageErrors: string[] = [];
    const failedHttp: string[] = [];
    page.on("response", (response) => {
      if (response.status() >= 400)
        failedHttp.push(`${String(response.status())} ${new URL(response.url()).pathname}`);
    });
    watchErrors(page, pageErrors);
    page.on("console", (msg) => {
      const text = msg.text();
      // Next.js streaming SSR hides the caret while chunks flush; the dev React
      // build logs it as a hydration mismatch. Production does not emit this.
      if (msg.type() === "error" && !devNoise(text)) pageErrors.push(text);
    });
    await authenticate(page);
    await page.goto(`${adminsBase}/access?view=entities`);
    await expect(main(page).getByRole("heading", { level: 1, name: /Access model/ })).toBeVisible();
    const entities = main(page).getByRole("table", { name: "Entities & actions" });
    await expect(entities.getByRole("columnheader", { name: "Discovery" })).toBeVisible();
    await expect(entities.getByRole("columnheader", { name: "Relations" })).toBeVisible();
    await entities.getByRole("button", { name: "Open Teams details" }).click();
    const drawer = page.getByRole("dialog", { name: "Teams", exact: true });
    await expect(drawer.getByRole("heading", { name: /Available actions/ })).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Actions", exact: true })).toBeVisible();
    await screenshot(page, info, "entity-drawer");
    await drawer.getByRole("button", { name: "Close", exact: true }).click();
    await expect(drawer).toBeHidden();
    await screenshot(page, info, "access-entities");
    await main(page)
      .getByRole("link", { name: /matrix|sections/i })
      .first()
      .click();
    await expect(page).toHaveURL(/view=matrix/, { timeout: urlTimeout });
    await fitsViewport(page);
    const sections = main(page).getByRole("table", { name: "Sections", exact: true });
    await expect(sections.getByRole("columnheader", { name: "Visible when" })).toBeVisible();
    await sections.getByRole("button", { name: "Open Overview details" }).click();
    await expect(
      page
        .getByRole("dialog", { name: "Section details" })
        .getByRole("link", { name: "Open section" }),
    ).toBeVisible();
    await screenshot(page, info, "access-sections");
    await page.getByRole("dialog").getByRole("button", { name: "Close", exact: true }).click();
    await main(page).getByRole("link", { name: "Role matrix", exact: true }).click();
    await expect(main(page).getByRole("table", { name: "Role matrix", exact: true })).toBeVisible();
    await screenshot(page, info, "access-matrix");
    expect(
      pageErrors,
      `Access model must render without formatting or runtime errors; HTTP failures: ${failedHttp.join(", ")}`,
    ).toEqual([]);
  });

  test("roles list keeps built-ins read-only and edits custom roles offline", async ({
    page,
  }, info) => {
    test.setTimeout(180_000);
    page.setDefaultTimeout(30_000);
    const pageErrors: string[] = [];
    watchErrors(page, pageErrors);
    await authenticate(page);
    await page.goto(`${adminsBase}/roles`);
    await expect(main(page).getByRole("heading", { level: 1, name: "Roles" })).toBeVisible();
    await fitsViewport(page);
    const roleList = main(page).getByRole("navigation", { name: "Roles", exact: true });
    await roleList.getByRole("button", { name: /^Superadmin Full/ }).click();
    await expect(page).toHaveURL(/role=superadmin/, { timeout: urlTimeout });
    await expect(main(page).getByRole("table", { name: "Permissions", exact: true })).toBeVisible();
    await expect(main(page).getByRole("button", { name: "Edit role", exact: true })).toHaveCount(0);
    await roleList.getByRole("button", { name: "Open Team lead details" }).click();
    await expect(page.getByRole("dialog", { name: "Role details" })).toBeVisible();
    await screenshot(page, info, "roles");
    await page.getByRole("dialog").getByRole("button", { name: "Close", exact: true }).click();
    test.skip(mode !== "offline", "Role mutation uses the offline fixture");
    const name = `e2e_role_${Date.now() % 1_000_000}`;
    await main(page).getByRole("button", { name: "Create role", exact: true }).click();
    const editor = page.getByRole("dialog", { name: "Create role", exact: true });
    await editor.locator("#role-create-name").fill(name);
    await editor.getByRole("checkbox", { name: "member.list", exact: true }).check();
    await editor.getByRole("button", { name: "Create", exact: true }).click();
    await expect(editor.getByText("Created", { exact: true })).toBeVisible({ timeout: urlTimeout });
    await editor.getByRole("button", { name: "Cancel", exact: true }).click();
    await roleList.getByRole("button", { name: new RegExp(`^${name} `) }).click();
    await main(page).getByRole("button", { name: "Edit role", exact: true }).click();
    const edit = page.getByRole("dialog", { name: "Edit role", exact: true });
    await edit.getByRole("checkbox", { name: "team.list", exact: true }).check();
    await edit.getByRole("button", { name: "Save changes", exact: true }).click();
    await expect(edit.getByText("Created", { exact: true })).toBeVisible({ timeout: urlTimeout });
    await edit.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(main(page).locator('[aria-label="team.list: Granted"]')).toBeVisible();
    expect(pageErrors, "Browser runtime errors are failures").toEqual([]);
  });

  test("employee access explains sources and follows scope selection", async ({ page }, info) => {
    test.setTimeout(180_000);
    page.setDefaultTimeout(30_000);
    const pageErrors: string[] = [];
    watchErrors(page, pageErrors);
    await authenticate(page);
    await page.goto(`${adminsBase}/employees`);
    const table = main(page).getByRole("table", { name: "Employee", exact: true });
    await expect(
      table.getByRole("columnheader", { name: "Access level", exact: true }),
    ).toBeVisible();
    await expect(main(page).getByRole("button", { name: "Add member", exact: true })).toHaveCount(
      0,
    );
    await table
      .getByRole("button", { name: /^Open .* details$/ })
      .first()
      .click();
    await expect(page).toHaveURL(/employee=/, { timeout: urlTimeout });
    const drawer = page.getByRole("dialog");
    await expect(drawer.getByRole("heading", { name: /Effective permissions/ })).toBeVisible();
    await expect(drawer.getByRole("heading", { name: "Roles and assignments" })).toBeVisible();
    await drawer.getByRole("button", { name: "Profile", exact: true }).click();
    await expect(drawer.getByText("Contact", { exact: true })).toBeVisible();
    await drawer.getByRole("button", { name: "Access", exact: true }).click();
    const scope = drawer.locator("#access-scope");
    expect(await scope.locator("option").count()).toBeGreaterThan(1);
    const team = await scope.locator('option[value^="team:"]').first().getAttribute("value");
    if (team) {
      await scope.selectOption(team);
      await scope.locator("..").getByRole("button", { name: "Access", exact: true }).click();
      await expect(page).toHaveURL(/scope=team/, { timeout: urlTimeout });
      await expect(page).toHaveURL(/employee=/);
      await expect(drawer.getByRole("heading", { name: /Effective permissions/ })).toBeVisible();
    }
    if (mode === "offline") {
      await drawer
        .locator("summary")
        .filter({ hasText: /^Grant action$/ })
        .click();
      const technologyScope = await drawer
        .locator('#grant-scope option[value^="technology:"]')
        .first()
        .getAttribute("value");
      expect(technologyScope).toBeTruthy();
      await drawer.locator("#grant-scope").selectOption(technologyScope ?? "");
      await expect(drawer.locator('#grant-permission option[value="technology.read"]')).toHaveCount(
        1,
      );
      await expect(drawer.locator('#grant-permission option[value="team.list"]')).toHaveCount(0);
      await drawer
        .locator("#grant-scope")
        .selectOption(
          (await drawer
            .locator('#grant-scope option[value^="organization:"]')
            .getAttribute("value")) ?? "",
        );
      await drawer.locator("#grant-permission").selectOption("team.list");
      await drawer.getByRole("button", { name: "Grant action", exact: true }).click();
      await expect(drawer.getByText("Created", { exact: true })).toBeVisible({
        timeout: urlTimeout,
      });
      await expect(drawer.locator("li").getByText("Teams · List", { exact: true })).toBeVisible();
      await drawer
        .locator("summary")
        .filter({ hasText: /^Grant action$/ })
        .click();
    }
    await screenshot(page, info, "employee-access");
    await drawer.getByRole("button", { name: "Close", exact: true }).click();
    await expect(drawer).toBeHidden();
    await expect(page).not.toHaveURL(/employee=/);
    expect(pageErrors, "Browser runtime errors are failures").toEqual([]);
  });

  test("security lists service principals with lifecycle controls", async ({ page }) => {
    test.setTimeout(180_000);
    page.setDefaultTimeout(30_000);
    test.skip(mode !== "offline", "Principal lifecycle uses the offline fixture");
    const pageErrors: string[] = [];
    watchErrors(page, pageErrors);
    await authenticate(page);
    await page.goto(`${adminsBase}/security`);
    await expect(main(page).getByRole("heading", { name: "Service principals" })).toBeVisible();
    await expect(main(page).getByText("telemetry-ingest")).toBeVisible();
    await expect(
      main(page).getByRole("button", { name: "Suspend", exact: true }).first(),
    ).toBeVisible();
    expect(pageErrors, "Browser runtime errors are failures").toEqual([]);
  });

  test("people & access screens stay within a mobile viewport and expose the rail dialog", async ({
    page,
  }, info) => {
    test.setTimeout(240_000);
    page.setDefaultTimeout(30_000);
    await authenticate(page);
    await page.setViewportSize({ width: 390, height: 800 });
    for (const route of peopleAccessRoutes) {
      await page.goto(route);
      if (mode === "offline" && route === `${adminsBase}/settings`) {
        // The fixture can manage service principals, but has no landscape/telemetry
        // policy rights. Those principals now belong to Security.
        await expect(
          main(page).getByText("You do not have access to this landscape."),
        ).toBeVisible();
      } else {
        await expect(main(page).getByRole("heading", { level: 1 })).toBeVisible({
          timeout: urlTimeout,
        });
      }
      await fitsViewport(page);
      const bounds = await main(page).boundingBox();
      expect(bounds?.width, "The content column must use the mobile viewport").toBeGreaterThan(340);
    }
    const trigger = page.getByRole("button", { name: "Open menu", exact: true });
    await expect(trigger).toBeVisible();
    await trigger.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const people = dialog.getByRole("button", { name: "Expand People & Access", exact: true });
    if (await people.isVisible()) await people.click();
    await expect(dialog.getByRole("link", { name: "Members & Invitations" })).toBeVisible();
    await expect(dialog.getByRole("link", { name: "Access model" })).toBeVisible();
    await screenshot(page, info, "mobile-navigation");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await screenshot(page, info, "mobile-members");
  });
});
