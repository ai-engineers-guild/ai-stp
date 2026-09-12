import { apiRequest } from "@/lib/api/http";

import type {
  CorporateAuditList,
  CorporateBindingList,
  CorporateContext,
  CorporateMemberList,
  CorporateRoleList,
  CorporateServicePrincipalList,
  OrganizationListResponse,
  OrganizationSummary,
} from "./generated/types.gen";

export async function readCorporateWorkspace(sessionToken: string): Promise<{
  organization: OrganizationSummary;
  context: CorporateContext;
  members: CorporateMemberList | null;
  roles: CorporateRoleList | null;
  bindings: CorporateBindingList | null;
  servicePrincipals: CorporateServicePrincipalList | null;
  audit: CorporateAuditList | null;
} | null> {
  const organization = await readCorporateOrganization(sessionToken);
  if (!organization) return null;
  const organizationPath = `/v1/corporate/organizations/${organization.organization_id}`;
  const context = await apiRequest<CorporateContext>(`${organizationPath}/context`, {
    sessionToken,
  });
  const [members, roles, bindings, servicePrincipals, audit] = await Promise.all([
    context.capabilities.includes("member.list")
      ? apiRequest<CorporateMemberList>(`${organizationPath}/members`, { sessionToken })
      : Promise.resolve(null),
    context.capabilities.includes("role.list")
      ? apiRequest<CorporateRoleList>(`${organizationPath}/roles`, { sessionToken })
      : Promise.resolve(null),
    context.capabilities.includes("binding.list")
      ? apiRequest<CorporateBindingList>(`${organizationPath}/bindings`, { sessionToken })
      : Promise.resolve(null),
    context.capabilities.includes("service_principal.list")
      ? apiRequest<CorporateServicePrincipalList>(`${organizationPath}/service-principals`, {
          sessionToken,
        })
      : Promise.resolve(null),
    context.capabilities.includes("audit.list")
      ? apiRequest<CorporateAuditList>(`${organizationPath}/audit`, { sessionToken })
      : Promise.resolve(null),
  ]);
  return { organization, context, members, roles, bindings, servicePrincipals, audit };
}

export async function readCorporateOrganization(
  sessionToken: string,
): Promise<OrganizationSummary | null> {
  const organizations = await apiRequest<OrganizationListResponse>("/v1/organizations", {
    sessionToken,
  });
  return organizations.items.find((item) => item.kind === "corporate") ?? null;
}
