import { apiRequest } from "@/lib/api/http";

import type {
  CorporateAuditList,
  CorporateBindingList,
  CorporateContext,
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

export async function readCorporateDirectory(
  sessionToken: string,
  resource: "projects" | "teams" | "members",
) {
  const context = await readCorporateContext(sessionToken);
  if (!context) return null;
  const path = `/v1/corporate/organizations/${context.organization.organization_id}`;
  const items: Array<{
    id: string;
    name: string;
    state: string;
    description?: string;
    role?: string;
  }> =
    resource === "members"
      ? (await apiRequest<CorporateMemberList>(`${path}/members`, { sessionToken })).items.map(
          (item) => ({
            id: item.account_id,
            name: item.display_name ?? item.account_id,
            state: item.state,
            role: item.role,
          }),
        )
      : resource === "teams"
        ? (await apiRequest<CorporateTeamList>(`${path}/teams`, { sessionToken })).items.map(
            (item) => ({
              id: item.team_id,
              name: item.name,
              state: item.state,
              description: item.description,
            }),
          )
        : (await apiRequest<CorporateProjectList>(`${path}/projects`, { sessionToken })).items.map(
            (item) => ({
              id: item.project_id,
              name: item.name,
              state: item.lifecycle ?? item.state,
            }),
          );
  const roles =
    resource === "members" && context.capabilities.includes("role.list")
      ? await apiRequest<CorporateRoleList>(`${path}/roles`, { sessionToken })
      : null;
  return { context, items, roles };
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
    (resource === "teams" || resource === "projects") &&
    context.capabilities.includes("member.list")
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
  const projectMembers =
    resource === "projects" && context.capabilities.includes("member.list")
      ? await apiRequest<CorporateMemberList>(`${path}/projects/${resourceId}/members`, {
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
    projectMembers,
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
