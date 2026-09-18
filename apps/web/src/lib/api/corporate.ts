import { apiRequest } from "@/lib/api/http";
import { ApiError } from "@/lib/api/errors";

import type {
  CorporateAuditList,
  CorporateBindingList,
  CorporateContext,
  CorporateDirectoryQuery,
  CorporateDirectoryView,
  CorporateOverview,
  CorporateMemberList,
  CorporateRoleList,
  CorporateServicePrincipalList,
  CorporateProjectList,
  CorporateTeamList,
  CorporateTeamView,
  CorporateMember,
  CorporateRoleView,
  CorporateCatalogAssignmentList,
  OrganizationListResponse,
  OrganizationSummary,
  EmployeeTechnologyList,
} from "./generated/types.gen";

export async function readCorporateContext(sessionToken: string): Promise<CorporateContext | null> {
  const organization = await readCorporateOrganization(sessionToken);
  if (!organization) return null;
  return apiRequest<CorporateContext>(
    `/v1/corporate/organizations/${organization.organization_id}/context`,
    { sessionToken },
  );
}

export async function readCorporateOverview(
  sessionToken: string,
): Promise<CorporateOverview | null> {
  const organization = await readCorporateOrganization(sessionToken);
  if (!organization) return null;
  return apiRequest<CorporateOverview>(
    `/v1/corporate/organizations/${organization.organization_id}/overview`,
    { sessionToken },
  );
}

export async function readCorporateDirectory(
  sessionToken: string,
  resource: "projects" | "teams" | "members" | "technologies",
) {
  const context = await readCorporateContext(sessionToken);
  if (!context) return null;
  const path = `/v1/corporate/organizations/${context.organization.organization_id}`;
  const directory = await readCorporateDirectoryPages(
    sessionToken,
    context.organization.organization_id,
    { resource, include_archived: true },
  );
  const roles =
    resource === "members" && context.capabilities.includes("role.list")
      ? await apiRequest<CorporateRoleList>(`${path}/roles`, { sessionToken })
      : null;
  return { ...directory, context, roles };
}

export async function readCorporateDirectoryPages(
  sessionToken: string,
  organizationId: string,
  filters: Omit<CorporateDirectoryQuery, "offset" | "limit">,
): Promise<CorporateDirectoryView> {
  const items: CorporateDirectoryView["items"] = [];
  let page: CorporateDirectoryView;
  do {
    page = await apiRequest<CorporateDirectoryView>(
      `/v1/corporate/organizations/${organizationId}/directory`,
      {
        sessionToken,
        query: {
          ...filters,
          query: filters.query ?? undefined,
          is_lead: filters.is_lead ?? undefined,
          offset: items.length,
          limit: 256,
        },
      },
    );
    if (!page.items.length && items.length < page.total) {
      throw new ApiError({
        code: "AI_STP_UNAVAILABLE",
        status: 503,
        message: "Corporate directory pagination returned an incomplete collection",
      });
    }
    items.push(...page.items);
  } while (items.length < page.total);
  return { ...page, items };
}

export async function readCorporateWorkspace(
  sessionToken: string,
  includeAudit = true,
): Promise<{
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
    includeAudit && context.capabilities.includes("audit.list")
      ? apiRequest<CorporateAuditList>(`${organizationPath}/audit`, { sessionToken })
      : Promise.resolve(null),
  ]);
  return { organization, context, members, roles, bindings, servicePrincipals, audit };
}

export async function readCorporateAudit(
  sessionToken: string,
  cursor: Record<string, string | string[] | undefined> = {},
) {
  const context = await readCorporateContext(sessionToken);
  if (!context || !context.capabilities.includes("audit.list")) return null;
  const path = `/v1/corporate/organizations/${context.organization.organization_id}`;
  const [audit, members] = await Promise.all([
    apiRequest<CorporateAuditList>(`${path}/audit`, {
      sessionToken,
      query: { ...corporateAuditCursor(cursor), ...corporateAuditFilters(cursor) },
    }),
    context.capabilities.includes("member.list")
      ? apiRequest<CorporateMemberList>(`${path}/members`, { sessionToken })
      : null,
  ]);
  return { context, audit, members };
}

export function corporateAuditFilters(params: Record<string, string | string[] | undefined>) {
  const actor = params.actor_account_id;
  return typeof actor === "string" && /^account_[0-9A-HJKMNP-TV-Z]{26}$/.test(actor)
    ? { actor_account_id: actor }
    : {};
}

export function corporateAuditCursor(cursor: Record<string, string | string[] | undefined>) {
  const id = cursor.before_id;
  const date = cursor.before_created_at;
  return typeof id === "string" &&
    /^[1-9]\d*$/.test(id) &&
    Number.isSafeInteger(Number(id)) &&
    typeof date === "string" &&
    date.length <= 64 &&
    Number.isFinite(Date.parse(date))
    ? { before_id: id, before_created_at: date }
    : {};
}

export async function readCorporateResource(
  sessionToken: string,
  resource: "projects" | "teams" | "members" | "roles",
  resourceId: string,
) {
  const context = await readCorporateContext(sessionToken);
  if (!context) return null;
  const path = `/v1/corporate/organizations/${context.organization.organization_id}`;
  const [team, member, role, teams, members, projects] = await Promise.all([
    resource === "teams"
      ? apiRequest<CorporateTeamView>(`${path}/teams/${resourceId}`, { sessionToken })
      : null,
    resource === "members"
      ? apiRequest<CorporateMember>(`${path}/members/${resourceId}`, { sessionToken })
      : null,
    resource === "roles"
      ? apiRequest<CorporateRoleView>(`${path}/roles/${resourceId}`, { sessionToken })
      : null,
    (resource === "teams" || resource === "members") && context.capabilities.includes("team.list")
      ? apiRequest<CorporateTeamList>(`${path}/teams`, { sessionToken })
      : null,
    resource === "teams" && context.capabilities.includes("member.list")
      ? apiRequest<CorporateMemberList>(`${path}/members`, { sessionToken })
      : null,
    resource === "members" && context.capabilities.includes("project.list")
      ? apiRequest<CorporateProjectList>(`${path}/projects`, { sessionToken })
      : null,
  ]);
  const projectMemberships =
    resource === "members" && context.capabilities.includes("project.list")
      ? await apiRequest<CorporateProjectList>(`${path}/members/${resourceId}/projects`, {
          sessionToken,
        })
      : null;
  return {
    organization: context.organization,
    context: {
      ...context,
      teams: teams?.items ?? context.teams,
      projects: projects?.items ?? context.projects,
    },
    team,
    member,
    role,
    members,
    roles: null,
    projectMemberships,
  };
}

export async function readCorporateMemberAccess(sessionToken: string, accountId: string) {
  const context = await readCorporateContext(sessionToken);
  if (
    !context ||
    !context.capabilities.some((capability) =>
      ["member.update", "member.delete"].includes(capability),
    )
  )
    return null;
  const path = `/v1/corporate/organizations/${context.organization.organization_id}`;
  const [member, roles] = await Promise.all([
    apiRequest<CorporateMember>(`${path}/members/${accountId}`, { sessionToken }),
    context.capabilities.includes("role.list")
      ? apiRequest<CorporateRoleList>(`${path}/roles`, { sessionToken })
      : null,
  ]);
  return { context, organization: context.organization, member, roles };
}

export async function readEmployeeTechnologies(
  sessionToken: string,
  organizationId: string,
  accountId: string,
) {
  return apiRequest<EmployeeTechnologyList>(
    `/v1/corporate/organizations/${organizationId}/members/${accountId}/technologies`,
    { sessionToken, query: { limit: "256" } },
  );
}

export async function readTechnologyEmployees(
  sessionToken: string,
  organizationId: string,
  technologyId: string,
) {
  return apiRequest<EmployeeTechnologyList>(
    `/v1/corporate/organizations/${organizationId}/technologies/${technologyId}/employees`,
    { sessionToken, query: { limit: "256" } },
  );
}

export async function readCorporateOrganization(
  sessionToken: string,
): Promise<OrganizationSummary | null> {
  const organizations = await apiRequest<OrganizationListResponse>("/v1/organizations", {
    sessionToken,
  });
  return organizations.items.find((item) => item.kind === "corporate") ?? null;
}

export async function readCorporateCatalogAssignments(
  sessionToken: string,
  organizationId: string,
  subjectKind: "employee" | "team" | "project",
  subjectId: string,
) {
  const items: CorporateCatalogAssignmentList["items"] = [];
  let total = 0;
  do {
    const page = await apiRequest<CorporateCatalogAssignmentList>(
      `/v1/corporate/organizations/${organizationId}/catalog-assignments`,
      {
        sessionToken,
        query: {
          subject_kind: subjectKind,
          subject_id: subjectId,
          include_retired: "true",
          offset: String(items.length),
          limit: "256",
        },
      },
    );
    items.push(...page.items);
    total = page.total;
    if (!page.items.length) break;
  } while (items.length < total);
  return { items, total };
}
