import { apiRequest } from "@/lib/api/http";

import type {
  CorporateContext,
  CorporateMemberList,
  OrganizationListResponse,
  OrganizationSummary,
} from "./generated/types.gen";

export async function readCorporateWorkspace(sessionToken: string): Promise<{
  organization: OrganizationSummary;
  context: CorporateContext;
  members: CorporateMemberList | null;
} | null> {
  const organization = await readCorporateOrganization(sessionToken);
  if (!organization) return null;
  const organizationPath = `/v1/corporate/organizations/${organization.organization_id}`;
  const context = await apiRequest<CorporateContext>(`${organizationPath}/context`, {
    sessionToken,
  });
  const members = context.capabilities.includes("member.list")
    ? await apiRequest<CorporateMemberList>(`${organizationPath}/members`, { sessionToken })
    : null;
  return { organization, context, members };
}

export async function readCorporateOrganization(
  sessionToken: string,
): Promise<OrganizationSummary | null> {
  const organizations = await apiRequest<OrganizationListResponse>("/v1/organizations", {
    sessionToken,
  });
  return organizations.items.find((item) => item.kind === "corporate") ?? null;
}
