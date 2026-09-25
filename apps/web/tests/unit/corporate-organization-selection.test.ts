import { describe, expect, it } from "vitest";

import { resolveCorporateOrganization } from "@/lib/api/corporate";
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

describe("resolveCorporateOrganization", () => {
  it("falls back to the first membership when no preference is stored", () => {
    expect(resolveCorporateOrganization([ALPHA, BETA], undefined)).toBe(ALPHA);
    expect(resolveCorporateOrganization([ALPHA, BETA], null)).toBe(ALPHA);
  });

  it("resolves a stored preference that is a current membership", () => {
    expect(resolveCorporateOrganization([ALPHA, BETA], BETA.organization_id)).toBe(BETA);
  });

  it("ignores a preference naming a revoked or forged organization", () => {
    expect(resolveCorporateOrganization([ALPHA, BETA], "organization_forged000000000")).toBe(ALPHA);
  });

  it("ignores a preference naming a non-corporate membership", () => {
    // readCorporateOrganizations filters to kind === "corporate", so a personal
    // organization id can never match a resolved item.
    expect(resolveCorporateOrganization([ALPHA, BETA], PERSONAL.organization_id)).toBe(ALPHA);
  });

  it("returns null without memberships", () => {
    expect(resolveCorporateOrganization([], ALPHA.organization_id)).toBeNull();
  });
});
