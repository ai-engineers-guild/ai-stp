import { expect, test, type Page } from "@playwright/test";

/**
 * Multi-organization membership journey (SPEC-083 REQ-8317): the switcher
 * renders only for accounts holding two or more corporate memberships, stores
 * a session-scoped preference, and rebinds per-request context. Live mode
 * needs an authenticated storage-state file whose account belongs to at least
 * two corporate organizations; offline mode proves the single-membership
 * bound. Never creates or mutates live data.
 * AI_STP_CORPORATE_E2E=offline|live opts in; absent means not part of SaaS E2E.
 */
const mode = process.env["AI_STP_CORPORATE_E2E"];
const state = process.env["AI_STP_CORPORATE_STORAGE_STATE"];
const switcher = '[data-ui="corporate-organization-switcher"]';
test.use({
  ...(mode === "live" && state ? { storageState: state } : {}),
  trace: "off",
  video: "off",
});

async function authenticate(page: Page) {
  if (mode === "live") {
    expect(
      Boolean(state),
      "Live corporate verification requires AI_STP_CORPORATE_STORAGE_STATE; no session is fabricated",
    ).toBe(true);
    const me = await page.request.get("/v1/auth/me");
    expect(me.status(), "Existing real API session must be valid").toBe(200);
    return;
  }
  await page.goto("/en/login?returnTo=%2Fen%2Fcorporate%2Foverview");
  await page.getByRole("button", { name: /Continue with GitHub/i }).click();
  await expect(page).toHaveURL((url) => url.pathname === "/en/corporate/overview");
}

type OrganizationItem = {
  organization_id: string;
  kind: string;
  display_name: string;
};

async function corporateMemberships(page: Page): Promise<OrganizationItem[]> {
  const response = await page.request.get("/v1/organizations");
  expect(response.status()).toBe(200);
  const body = (await response.json()) as { items: OrganizationItem[] };
  return body.items.filter((item) => item.kind === "corporate");
}

test.describe("corporate organization selection", () => {
  test.skip(
    !mode,
    "Opt in after integration with AI_STP_CORPORATE_E2E=offline or live; this skip is not corporate verification",
  );

  test("single-membership accounts render no organization selector", async ({ page }) => {
    test.skip(
      mode !== "offline",
      "The offline fixture ships exactly one corporate membership; live membership counts vary",
    );
    await authenticate(page);
    await page.goto("/en/corporate/overview");
    await expect(page.locator(switcher)).toHaveCount(0);
  });

  test("members switch organizations and denied tenants stay denied", async ({ page }, info) => {
    test.skip(mode !== "live", "Multi-membership selection requires a real two-tenant session");
    await authenticate(page);
    const memberships = await corporateMemberships(page);
    test.skip(
      memberships.length < 2,
      `Session holds ${memberships.length} corporate membership(s); the switcher needs two`,
    );
    const [first, second] = memberships;
    if (!first || !second) throw new Error("Two corporate memberships are required");
    await page.goto("/en/corporate/overview");
    const control = page.locator(`${switcher} select`);
    await expect(control).toBeVisible();
    const options = await control.locator("option").allTextContents();
    expect(options).toContain(first.display_name);
    expect(options).toContain(second.display_name);

    const target = second;
    await control.selectOption(target.organization_id);
    await expect
      .poll(async () => {
        const jar = await page.context().cookies();
        return jar.find((cookie) => cookie.name === "ai_stp_corporate_org")?.value;
      })
      .toBe(target.organization_id);

    await page.goto("/en/corporate/overview");
    const contextResponse = await page.request.get(
      `/v1/corporate/organizations/${target.organization_id}/context`,
    );
    expect(
      contextResponse.status(),
      "A selected membership must remain readable in its own tenant",
    ).toBe(200);

    const forged = "organization_zzzzzzzzzzzzzzzzzzzzzz";
    const denied = await page.request.get(`/v1/corporate/organizations/${forged}/overview`);
    expect(
      [401, 403, 404],
      "A foreign organization id must not resolve to a tenant the session operates in",
    ).toContain(denied.status());
    info.annotations.push({
      type: "backend",
      description: `Two corporate memberships verified; foreign id ${forged} rejected with ${denied.status()}`,
    });
  });
});
