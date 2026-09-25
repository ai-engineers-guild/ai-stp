import { beforeEach, describe, expect, it, vi } from "vitest";

import { CORPORATE_ORG_COOKIE, SESSION_COOKIE } from "@/lib/auth/cookies";
import type { OrganizationSummary } from "@/lib/api/generated/types.gen";

function organization(
  id: string,
  kind: "personal" | "corporate" = "corporate",
): OrganizationSummary {
  return {
    display_name: `Org ${id}`,
    kind,
    membership_revision: 1,
    organization_id: id,
    schema_version: 1,
  };
}

const ALPHA = organization("organization_alpha000000000000");
const BETA = organization("organization_beta0000000000000");
const PERSONAL = organization("organization_personal000000", "personal");

const jar = {
  get: vi.fn(),
  set: vi.fn(),
  delete: vi.fn(),
};

vi.mock("next/headers", () => ({ cookies: vi.fn(() => Promise.resolve(jar)) }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next-intl/server", () => ({
  getTranslations: vi.fn(() => Promise.resolve((key: string) => key)),
}));
vi.mock("@/lib/api/http", () => ({ privateApiRequest: vi.fn() }));
vi.mock("@/lib/api/corporate", () => ({
  corporateAuditFilters: vi.fn(),
  readCorporateContext: vi.fn(),
  readCorporateOrganizations: vi.fn(),
}));
vi.mock("@/lib/auth/session", () => ({
  assertCsrf: vi.fn(),
  readCsrfToken: vi.fn(),
  readSession: vi.fn(() => Promise.resolve({ accountId: "account_x" })),
  SESSION_COOKIE: "ai_stp_session",
  SESSION_TTL_MS: 12 * 60 * 60 * 1000,
}));
vi.mock("@/lib/features/compiled", () => ({ COMPILED_FEATURE_PROFILE: "corporate_hub" }));

const { readCorporateOrganizations } = await import("@/lib/api/corporate");
const { readSession } = await import("@/lib/auth/session");
const { selectCorporateOrganization } = await import("@/actions/corporate");

describe("selectCorporateOrganization", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    jar.get.mockReturnValue({ value: "session-token" });
  });

  it("stores a preference for a current corporate membership", async () => {
    vi.mocked(readCorporateOrganizations).mockResolvedValue([ALPHA, BETA]);
    const form = new FormData();
    form.set("organization", BETA.organization_id);
    await selectCorporateOrganization(form);
    expect(jar.set).toHaveBeenCalledWith(
      CORPORATE_ORG_COOKIE,
      BETA.organization_id,
      expect.objectContaining({ httpOnly: true, sameSite: "lax", path: "/" }),
    );
    expect(jar.delete).not.toHaveBeenCalled();
  });

  it("clears the preference instead of storing a non-membership value", async () => {
    vi.mocked(readCorporateOrganizations).mockResolvedValue([ALPHA]);
    const form = new FormData();
    form.set("organization", "organization_forged000000000");
    await selectCorporateOrganization(form);
    expect(jar.set).not.toHaveBeenCalled();
    expect(jar.delete).toHaveBeenCalledWith(CORPORATE_ORG_COOKIE);
  });

  it("rejects a preference naming a personal organization", async () => {
    vi.mocked(readCorporateOrganizations).mockResolvedValue([ALPHA]);
    const form = new FormData();
    form.set("organization", PERSONAL.organization_id);
    await selectCorporateOrganization(form);
    expect(jar.set).not.toHaveBeenCalled();
    expect(jar.delete).toHaveBeenCalledWith(CORPORATE_ORG_COOKIE);
  });

  it("does nothing without an authenticated session", async () => {
    jar.get.mockImplementation((name: string) =>
      name === SESSION_COOKIE ? undefined : { value: "other" },
    );
    const form = new FormData();
    form.set("organization", ALPHA.organization_id);
    await selectCorporateOrganization(form);
    expect(readCorporateOrganizations).not.toHaveBeenCalled();
    expect(jar.set).not.toHaveBeenCalled();
  });

  it("does nothing when the session cookie is stale", async () => {
    vi.mocked(readSession).mockResolvedValueOnce(null);
    const form = new FormData();
    form.set("organization", ALPHA.organization_id);
    await selectCorporateOrganization(form);
    expect(readCorporateOrganizations).not.toHaveBeenCalled();
    expect(jar.set).not.toHaveBeenCalled();
  });
});
