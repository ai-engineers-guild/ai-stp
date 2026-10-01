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
  if (mode === "live") {
    expect(
      Boolean(state),
      "Live corporate verification requires AI_STP_CORPORATE_STORAGE_STATE",
    ).toBe(true);
    const me = await page.request.get("/v1/auth/me");
    expect(me.status(), "Existing real API session must be valid").toBe(200);
    return;
  }
  await page.goto("/en/login?returnTo=%2Fen%2Fcorporate%2Faccount");
  await page.getByRole("button", { name: /Continue with GitHub/i }).click();
  await page.waitForURL("**/en/corporate/account", { timeout: urlTimeout });
}

async function screenshot(page: Page, info: TestInfo, name: string) {
  const directory = path.resolve(process.cwd(), "../../.impeccable/review");
  await mkdir(directory, { recursive: true });
  const file = path.join(directory, `people-access-${mode}-${info.project.name}-${name}.png`);
  await page.screenshot({ path: file, fullPage: name !== "mobile-navigation" });
  await info.attach(name, { path: file, contentType: "image/png" });
}

async function fitsViewport(page: Page) {
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
}

test.describe("People & Access administration", () => {
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
    await expect(main(page).getByRole("heading", { name: "member" })).toBeVisible();
    await screenshot(page, info, "access-entities");
    await main(page)
      .getByRole("link", { name: /matrix|sections/i })
      .first()
      .click();
    await expect(page).toHaveURL(/view=matrix/, { timeout: urlTimeout });
    await fitsViewport(page);
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
    await expect(main(page).getByRole("link", { name: "superadmin" })).toBeVisible();
    await screenshot(page, info, "roles");
    await main(page).getByRole("link", { name: "superadmin" }).click();
    await expect(page).toHaveURL(/role=superadmin/, { timeout: urlTimeout });
    await expect(
      main(page).getByRole("region", { name: "superadmin" }).getByRole("button", {
        name: "Delete",
        exact: true,
      }),
      "Built-in roles must not offer destructive actions",
    ).toHaveCount(0);
    test.skip(mode !== "offline", "Role mutation uses the offline fixture");
    const name = `e2e_role_${Date.now() % 1_000_000}`;
    await main(page).getByText("Create role").click();
    await main(page).locator("#role-create-name").fill(name);
    await main(page).locator("#role-create-permissions").fill("member.list");
    await main(page)
      .locator("form", { has: page.locator("#role-create-name") })
      .getByRole("button", { name: "Create", exact: true })
      .click();
    await expect(main(page).getByRole("link", { name, exact: true })).toBeVisible({
      timeout: urlTimeout,
    });
    expect(pageErrors, "Browser runtime errors are failures").toEqual([]);
  });

  test("employee access explains sources and follows scope selection", async ({ page }, info) => {
    test.setTimeout(180_000);
    page.setDefaultTimeout(30_000);
    const pageErrors: string[] = [];
    watchErrors(page, pageErrors);
    await authenticate(page);
    await page.goto(adminsBase);
    await main(page)
      .locator("tbody")
      .getByRole("button", { name: /Actions for/ })
      .first()
      .click();
    await page.getByRole("menuitem", { name: "Manage access", exact: true }).click();
    await expect(page).toHaveURL(/\/admins\/employees\//, { timeout: urlTimeout });
    await expect(
      main(page).getByRole("heading", { level: 1, name: "Employee access" }),
    ).toBeVisible();
    await expect(main(page).getByRole("heading", { name: "Effective access" })).toBeVisible();
    await expect(main(page).getByRole("heading", { name: "Private catalog grants" })).toBeVisible();
    const scope = main(page).locator("#access-scope");
    await expect(scope).toBeVisible();
    const options = await scope.locator("option").count();
    expect(options, "Scope selector must offer organization, teams and projects").toBeGreaterThan(
      1,
    );
    const team = await scope.locator('option[value^="team:"]').first().getAttribute("value");
    if (team) {
      await scope.selectOption(team);
      await main(page).getByRole("button", { name: "Access", exact: true }).click();
      await expect(page).toHaveURL(/scope=team/, { timeout: urlTimeout });
      await expect(main(page).getByRole("heading", { name: "Effective access" })).toBeVisible();
    }
    await screenshot(page, info, "employee-access");
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
