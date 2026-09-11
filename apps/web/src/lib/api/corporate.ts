import { apiRequest } from "@/lib/api/http";

import type {
  CorporateContext,
  OrganizationListResponse,
  OrganizationSummary,
} from "./generated/types.gen";

export async function readCorporateWorkspace(
  sessionToken: string,
): Promise<{ organization: OrganizationSummary; context: CorporateContext } | null> {
  const organization = await readCorporateOrganization(sessionToken);
  if (!organization) return null;
  const context = await apiRequest<CorporateContext>(
    `/v1/corporate/organizations/${organization.organization_id}/context`,
    { sessionToken },
  );
  return { organization, context };
}

export async function readCorporateOrganization(
  sessionToken: string,
): Promise<OrganizationSummary | null> {
  const organizations = await apiRequest<OrganizationListResponse>("/v1/organizations", {
    sessionToken,
  });
  return organizations.items.find((item) => item.kind === "corporate") ?? null;
}
