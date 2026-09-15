import { privateApiRequest } from "@/lib/api/http";
import { ApiError, mapHttpError, type ReadState } from "@/lib/api/errors";
import { readCorporateDirectoryPages, readCorporateOrganization } from "./corporate";

import type {
  CapabilityProjection,
  CategoryList,
  CategoryView,
  TechnologyList,
  TechnologyLandscapeView,
  TechnologyView,
  CorporateProjectView,
  ProjectTechnologyList,
  TechnologyLandscapePolicyView,
  TechnologyDecisionView,
  TechnologyTeamList,
  ProjectTeamList,
  CorporateTeamList,
  CorporateTeamView,
  CorporateProjectList,
  CorporateMemberList,
} from "./generated/types.gen";

async function readGovernedProjection<T>(
  path: string,
  sessionToken: string,
  allowEmpty: boolean,
): Promise<ReadState<T>> {
  try {
    return { status: "data", data: await privateApiRequest<T>(path, { sessionToken }) };
  } catch (error) {
    if (allowEmpty && error instanceof ApiError && error.status === 404) return { status: "empty" };
    return { status: "error", error: error instanceof ApiError ? error : mapHttpError(0, {}) };
  }
}

export async function readTechnologyCapabilities(
  sessionToken: string,
  organizationId: string,
  scope?: { kind: "project" | "team" | "technology"; id: string },
): Promise<CapabilityProjection> {
  return privateApiRequest<CapabilityProjection>(
    `/v1/organizations/${organizationId}/capabilities`,
    {
      sessionToken,
      ...(scope ? { query: { scope_kind: scope.kind, scope_id: scope.id } } : {}),
    },
  );
}

export async function readTechnologyRegistry(
  sessionToken: string,
  organizationId: string,
  query?: string,
) {
  const permissions = await readTechnologyCapabilities(sessionToken, organizationId);
  const path = `/v1/corporate/organizations/${organizationId}`;
  const [technologies, categories] = await Promise.all([
    permissions.capabilities.includes("technology.list")
      ? privateApiRequest<TechnologyList>(`${path}/technologies`, {
          sessionToken,
          ...(query ? { query: { query } } : {}),
        })
      : null,
    permissions.capabilities.includes("category.list") &&
    permissions.capabilities.includes("category.read")
      ? privateApiRequest<CategoryList>(`${path}/technology-categories`, { sessionToken })
      : null,
  ]);
  return { permissions, technologies, categories };
}

export async function readTechnologyDirectory(sessionToken: string) {
  const organization = await readCorporateOrganization(sessionToken);
  if (!organization) return null;
  const permissions = await readTechnologyCapabilities(sessionToken, organization.organization_id);
  const [directory, categories] = await Promise.all([
    permissions.capabilities.includes("technology.list")
      ? readCorporateDirectoryPages(sessionToken, organization.organization_id, {
          resource: "technologies",
          include_archived: true,
        })
      : null,
    permissions.capabilities.includes("category.list") &&
    permissions.capabilities.includes("category.read")
      ? privateApiRequest<CategoryList>(
          `/v1/corporate/organizations/${organization.organization_id}/technology-categories`,
          { sessionToken },
        )
      : null,
  ]);
  return { organization, permissions, directory, categories };
}

export async function readCategoryDirectory(sessionToken: string, organizationId: string) {
  const permissions = await readTechnologyCapabilities(sessionToken, organizationId);
  if (!permissions.capabilities.includes("category.list")) return null;
  const categories = await privateApiRequest<CategoryList>(
    `/v1/corporate/organizations/${organizationId}/technology-categories`,
    { sessionToken },
  );
  return { permissions, categories };
}

export async function readCategoryDetail(
  sessionToken: string,
  organizationId: string,
  categoryId: string,
) {
  const permissions = await readTechnologyCapabilities(sessionToken, organizationId);
  if (!permissions.capabilities.includes("category.read")) return null;
  const path = `/v1/corporate/organizations/${organizationId}`;
  const [category, technologies] = await Promise.all([
    privateApiRequest<CategoryView>(`${path}/technology-categories/${categoryId}`, {
      sessionToken,
    }),
    permissions.capabilities.includes("technology.list")
      ? readCategoryTechnologies(sessionToken, path, categoryId)
      : null,
  ]);
  return { permissions, category, technologies };
}

async function readCategoryTechnologies(
  sessionToken: string,
  path: string,
  categoryId: string,
): Promise<TechnologyList> {
  const items: TechnologyView[] = [];
  let offset = 0;
  let total = 0;
  do {
    const page = await privateApiRequest<TechnologyList>(`${path}/technologies`, {
      sessionToken,
      query: { offset: String(offset), limit: "256" },
    });
    items.push(...page.items.filter((item) => item.category_ids.includes(categoryId)));
    offset += page.items.length;
    total = page.total;
    if (!page.items.length) break;
  } while (offset < total);
  return { items, total: items.length };
}

export async function readTechnologyDetail(
  sessionToken: string,
  organizationId: string,
  technologyId: string,
) {
  const permissions = await readTechnologyCapabilities(sessionToken, organizationId, {
    kind: "technology",
    id: technologyId,
  });
  if (!permissions.capabilities.includes("technology.read")) return null;
  const path = `/v1/corporate/organizations/${organizationId}`;
  const dictionaryPermissions =
    (permissions.capabilities.includes("category.list") &&
      permissions.capabilities.includes("category.read")) ||
    permissions.capabilities.includes("team.list") ||
    permissions.capabilities.includes("member.list")
      ? await readTechnologyCapabilities(sessionToken, organizationId)
      : null;
  const [technology, categories, decision, teams, availableTeams, members] = await Promise.all([
    privateApiRequest<TechnologyView>(`${path}/technologies/${technologyId}`, { sessionToken }),
    dictionaryPermissions?.capabilities.includes("category.list") &&
    dictionaryPermissions.capabilities.includes("category.read")
      ? privateApiRequest<CategoryList>(`${path}/technology-categories`, { sessionToken })
      : null,
    permissions.capabilities.includes("technology_decision.read")
      ? readGovernedProjection<TechnologyDecisionView>(
          `${path}/technologies/${technologyId}/decision`,
          sessionToken,
          true,
        )
      : null,
    permissions.capabilities.includes("technology_team.list") &&
    permissions.capabilities.includes("technology_team.read")
      ? readGovernedProjection<TechnologyTeamList>(
          `${path}/technologies/${technologyId}/responsible-teams?include_history=true`,
          sessionToken,
          false,
        )
      : null,
    dictionaryPermissions?.capabilities.includes("team.list")
      ? privateApiRequest<CorporateTeamList>(`${path}/teams`, { sessionToken })
      : null,
    dictionaryPermissions?.capabilities.includes("member.list")
      ? privateApiRequest<CorporateMemberList>(`${path}/members`, { sessionToken })
      : null,
  ]);
  const teamDirectory = availableTeams?.items ?? [];
  const relatedTeamIds =
    teams?.status === "data" ? teams.data.items.map((item) => item.team_id) : [];
  const missingTeamIds = [...new Set(relatedTeamIds)].filter(
    (id) => !teamDirectory.some((item) => item.team_id === id),
  );
  const relatedTeams = await Promise.all(
    missingTeamIds.map((id) =>
      privateApiRequest<CorporateTeamView>(`${path}/teams/${id}`, { sessionToken }),
    ),
  );
  return {
    permissions,
    technology,
    categories,
    decision,
    teams,
    availableTeams: [...teamDirectory, ...relatedTeams],
    members: members?.items ?? [],
    projects:
      permissions.capabilities.includes("project_technology.list") &&
      permissions.capabilities.includes("project_technology.read")
        ? await readTechnologyProjects(sessionToken, organizationId, technologyId)
        : null,
  };
}

export async function readTechnologyProjects(
  sessionToken: string,
  organizationId: string,
  technologyId: string,
): Promise<ReadState<{ relations: ProjectTechnologyList; projects: CorporateProjectView[] }>> {
  const path = `/v1/corporate/organizations/${organizationId}`;
  try {
    const items: ProjectTechnologyList["items"] = [];
    let total = 0;
    do {
      const page = await privateApiRequest<ProjectTechnologyList>(
        `${path}/technologies/${technologyId}/projects`,
        {
          sessionToken,
          query: { offset: String(items.length), limit: "256" },
        },
      );
      items.push(...page.items);
      total = page.total;
      if (!page.items.length) break;
    } while (items.length < total);
    // Read only subjects authorized by the reverse relation projection, not the whole directory.
    const projects = await Promise.all(
      [...new Set(items.map((item) => item.project_id))].map((id) =>
        privateApiRequest<CorporateProjectView>(`${path}/projects/${id}`, { sessionToken }),
      ),
    );
    return { status: "data", data: { relations: { items, total }, projects } };
  } catch (error) {
    return { status: "error", error: error instanceof ApiError ? error : mapHttpError(0, {}) };
  }
}

export async function readProjectTechnologyDetail(
  sessionToken: string,
  organizationId: string,
  projectId: string,
) {
  const permissions = await readTechnologyCapabilities(sessionToken, organizationId, {
    kind: "project",
    id: projectId,
  });
  if (!permissions.capabilities.includes("project.read")) return null;
  const path = `/v1/corporate/organizations/${organizationId}/projects/${projectId}`;
  const [project, relations, registry, projectTeams, teams] = await Promise.all([
    privateApiRequest<CorporateProjectView>(path, { sessionToken }),
    permissions.capabilities.includes("project_technology.list") &&
    permissions.capabilities.includes("project_technology.read")
      ? privateApiRequest<ProjectTechnologyList>(`${path}/technologies`, {
          sessionToken,
          query: { include_history: "true" },
        })
      : null,
    permissions.capabilities.includes("technology.list")
      ? privateApiRequest<TechnologyList>(
          `/v1/corporate/organizations/${organizationId}/technologies`,
          { sessionToken },
        )
      : null,
    permissions.capabilities.includes("project_team.list") &&
    permissions.capabilities.includes("project_team.read")
      ? privateApiRequest<ProjectTeamList>(`${path}/teams`, { sessionToken })
      : null,
    permissions.capabilities.includes("team.list")
      ? privateApiRequest<CorporateTeamList>(
          `/v1/corporate/organizations/${organizationId}/teams`,
          { sessionToken },
        )
      : null,
  ]);
  return {
    project,
    relations,
    permissions,
    technologies: registry?.items ?? [],
    projectTeams,
    teams: teams?.items ?? [],
  };
}

export async function readTeamProjects(
  sessionToken: string,
  organizationId: string,
  teamId: string,
) {
  const permissions = await readTechnologyCapabilities(sessionToken, organizationId, {
    kind: "team",
    id: teamId,
  });
  if (
    !permissions.capabilities.includes("project_team.list") ||
    !permissions.capabilities.includes("project_team.read")
  )
    return null;
  const path = `/v1/corporate/organizations/${organizationId}`;
  const [relations, projects] = await Promise.all([
    privateApiRequest<ProjectTeamList>(`${path}/teams/${teamId}/projects`, { sessionToken }),
    permissions.capabilities.includes("project.list")
      ? privateApiRequest<CorporateProjectList>(`${path}/projects`, { sessionToken })
      : null,
  ]);
  return { relations, projects, permissions };
}

export async function readTechnologyLandscapePolicy(sessionToken: string, organizationId: string) {
  return privateApiRequest<TechnologyLandscapePolicyView>(
    `/v1/corporate/organizations/${organizationId}/technology-landscape-policy`,
    { sessionToken },
  );
}

export const LANDSCAPE_FILTER_KEYS = [
  "view",
  "query",
  "category_id",
  "technology_id",
  "project_id",
  "team_id",
  "lifecycle",
  "project_lifecycle",
  "activity",
  "source_availability",
  "adoption",
  "context",
  "review",
  "freshness",
  "include_history",
  "include_inactive",
  "offset",
  "limit",
  "project_offset",
  "project_limit",
] as const;

export function landscapeFilters(params: Record<string, string | string[] | undefined>) {
  return Object.fromEntries(
    LANDSCAPE_FILTER_KEYS.flatMap((key) => {
      const value = params[key];
      return typeof value === "string" && value ? [[key, value]] : [];
    }),
  );
}

export async function readTechnologyLandscape(
  sessionToken: string,
  organizationId: string,
  filters: Record<string, string>,
): Promise<TechnologyLandscapeView> {
  return privateApiRequest<TechnologyLandscapeView>(
    `/v1/corporate/organizations/${organizationId}/technology-landscape`,
    { sessionToken, query: filters },
  );
}
