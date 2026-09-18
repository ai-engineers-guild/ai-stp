import { afterEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  session: vi.fn(),
  token: vi.fn(),
  context: vi.fn(),
}));
vi.mock("@/lib/auth/session", () => ({ readSession: mocks.session }));
vi.mock("@/lib/auth/require-session", () => ({ sessionCookieValue: mocks.token }));
vi.mock("@/lib/api/corporate", () => ({ readCorporateContext: mocks.context }));

afterEach(() => {
  vi.resetModules();
  vi.resetAllMocks();
  vi.unstubAllEnvs();
});

it("orders corporate destinations and fails closed for administration", async () => {
  vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "corporate_hub");
  const { siteNavigation } = await import("@/lib/projection/navigation");
  const input = { signedIn: true, docsHref: "https://docs.test" };
  expect(
    siteNavigation(input)
      .slice(1, 6)
      .map((item) => item.href),
  ).toEqual([
    "/corporate/overview",
    "/catalog",
    "/corporate/organization",
    "/corporate/technology-landscape",
    "/corporate/dashboard",
  ]);
  expect(siteNavigation(input).some((item) => item.labelKey === "admins")).toBe(false);
  expect(siteNavigation({ ...input, corporateAdministration: true })[6]?.labelKey).toBe("admins");
  expect(
    siteNavigation({ ...input, signedIn: false, corporateAdministration: true }).some(
      (item) => item.labelKey === "admins",
    ),
  ).toBe(false);
});

it("retains personal SaaS navigation", async () => {
  vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "public_saas");
  vi.stubEnv("AI_STP_COMPILED_FEATURE_CONTENT_HUB", "true");
  vi.stubEnv("AI_STP_COMPILED_FEATURE_SAAS_PUBLIC_PAGES", "true");
  const { siteNavigation } = await import("@/lib/projection/navigation");
  const paths = siteNavigation({ signedIn: false, docsHref: "https://docs.test" }).map(
    (item) => item.href,
  );
  expect(paths).toEqual([
    "/",
    "/catalog",
    "/services",
    "https://docs.test",
    "/content",
    "/contact",
    "/login",
  ]);
});

it("highlights the corporate destination that owns the current route", async () => {
  vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "corporate_hub");
  const { isPrimaryNavigationActive, siteNavigation } = await import("@/lib/projection/navigation");
  const items = siteNavigation({ signedIn: true, docsHref: "https://docs.test" });
  const organization = items.find((item) => item.labelKey === "organization");
  const landscape = items.find((item) => item.labelKey === "landscape");
  const admins = siteNavigation({
    signedIn: true,
    docsHref: "https://docs.test",
    corporateAdministration: true,
  }).find((item) => item.labelKey === "admins");
  expect(organization && isPrimaryNavigationActive(organization, "/corporate/teams/team_1")).toBe(
    true,
  );
  expect(landscape && isPrimaryNavigationActive(landscape, "/corporate/categories")).toBe(true);
  expect(
    organization && isPrimaryNavigationActive(organization, "/corporate/organization/admins"),
  ).toBe(false);
  expect(admins && isPrimaryNavigationActive(admins, "/corporate/organization/admins")).toBe(true);
});

it("does not load corporate data for an unauthenticated visitor", async () => {
  vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "corporate_hub");
  mocks.session.mockResolvedValue(null);
  const { GET } = await import("@/app/api/corporate/navigation/route");
  const response = await GET();
  expect(await response.json()).toEqual({ administration: false });
  expect(response.headers.get("Cache-Control")).toBe("no-store, private");
  expect(mocks.context).not.toHaveBeenCalled();
});

it.each([
  ["audit.list", true],
  ["team.list", false],
])("resolves %s authority on the server", async (capability, administration) => {
  vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "corporate_hub");
  mocks.session.mockResolvedValue({ accountId: "account_test" });
  mocks.token.mockResolvedValue("session-token");
  mocks.context.mockResolvedValue({ capabilities: [capability] });
  const { GET } = await import("@/app/api/corporate/navigation/route");
  expect(await (await GET()).json()).toEqual({ administration });
  expect(mocks.context).toHaveBeenCalledWith("session-token");
});
