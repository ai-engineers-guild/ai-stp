import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound, permanentRedirect } from "next/navigation";

import { StatePanel } from "@/components/molecules/state-panel";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { LocalizedResourceDeleteMenuItem } from "@/components/organisms/localized-corporate-resource-actions";
import { CorporateCatalogAssignments } from "@/components/organisms/corporate-catalog-assignments";
import { CorporateRelationSection } from "@/components/organisms/corporate-relation-section";
import { relationSectionLabels } from "@/components/organisms/corporate-directory-types";
import { CorporateEmployeeDetail } from "@/components/organisms/corporate-employee-detail";
import { corporateEmployeeDetailLabels } from "@/components/organisms/corporate-employee-labels";
import { CorporateEntityDetail } from "@/components/organisms/corporate-entity-detail";
import { assignmentCardItem } from "@/lib/assignment-card";
import type { OwnerCardItem } from "@/components/organisms/object-card";
import { readCorporatePresentation } from "@/lib/api/corporate-detail";
import {
  assembleCorporateEmployeePresentation,
  readCorporateEmployeeContent,
} from "@/lib/api/corporate-employee";
import { ApiError } from "@/lib/api/errors";
import { readCorporateResource, readCorporateCatalogAssignments } from "@/lib/api/corporate";
import { readProjectTechnologyDetail } from "@/lib/api/technology";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { mapPool, readAssignedObjectSummary } from "@/lib/catalog-load";
import { safeCorporateQuery } from "@/lib/corporate-routes";

type PageProps = {
  params: Promise<{ locale: string; resource: string; resourceId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

// eslint-disable-next-line complexity, max-lines-per-function
export default async function CorporateResourcePage({ params, searchParams }: PageProps) {
  const { locale, resource: rawResource, resourceId } = await params;
  const filters = await searchParams;
  if (rawResource === "members") {
    permanentRedirect(
      `/${locale}/corporate/employees/${encodeURIComponent(resourceId)}${safeCorporateQuery(filters)}`,
    );
  }
  const resource = rawResource === "employees" ? "members" : rawResource;
  const directoryQuery = new URLSearchParams({
    ...(typeof filters.query === "string" ? { query: filters.query } : {}),
    ...(typeof filters.status === "string" ? { status: filters.status } : {}),
  }).toString();
  if (
    resource !== "projects" &&
    resource !== "teams" &&
    resource !== "members" &&
    resource !== "roles"
  )
    notFound();
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/${resource}/${resourceId}`);
  const t = await getTranslations("corporate");
  const tc = await getTranslations("common");
  const h = await getTranslations("hub");
  const session = (await sessionCookieValue()) ?? "";

  let workspace;
  try {
    workspace = await readCorporateResource(session, resource, resourceId);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.code === "AI_STP_NOT_FOUND" || error.status === 404) notFound();
      return (
        <StatePanel
          kind="error"
          title={tc("error")}
          description={
            error.code === "AI_STP_RATE_LIMITED" ? tc("apiRateLimited") : tc("apiUnavailable")
          }
        />
      );
    }
    throw error;
  }
  if (!workspace) notFound();
  if (
    resource === "projects" &&
    !workspace.context.projects.some((item) => item.project_id === resourceId)
  ) {
    notFound();
  }

  let projectDetail = null;
  if (resource === "projects") {
    try {
      projectDetail = await readProjectTechnologyDetail(
        session,
        workspace.organization.organization_id,
        resourceId,
      );
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === "AI_STP_NOT_FOUND" || error.status === 404) notFound();
        return (
          <StatePanel
            kind="error"
            title={tc("error")}
            description={
              error.code === "AI_STP_RATE_LIMITED" ? tc("apiRateLimited") : tc("apiUnavailable")
            }
          />
        );
      }
      throw error;
    }
  }
  const project = projectDetail?.project;
  const team = workspace.team;
  const teamProjects = team
    ? workspace.context.projects.filter((project) => team.project_ids.includes(project.project_id))
    : [];
  const member = workspace.member;
  const employeeContent = member
    ? await readCorporateEmployeeContent({
        sessionToken: session,
        organizationId: workspace.organization.organization_id,
        accountId: member.account_id,
        canReadTechnologies: workspace.context.capabilities.includes("technology.list"),
      })
    : null;
  const role = workspace.role;
  const detail =
    resource === "projects"
      ? project && {
          id: project.project_id,
          name: project.name,
          state: project.lifecycle ?? project.state,
          revision: project.revision,
          role: undefined,
          title: t("projectDetails"),
          description: t("projectDetailsBody"),
        }
      : resource === "teams"
        ? team && {
            id: team.team_id,
            name: team.name,
            state: team.state,
            revision: team.revision,
            role: undefined,
            title: t("teamDetails"),
            description: t("teamDetailsBody"),
          }
        : resource === "members"
          ? member && {
              id: member.account_id,
              name: member.display_name?.trim() || t("unknownEmployee"),
              state: member.state,
              revision: member.revision,
              role: undefined,
              title: t("memberDetails"),
              description: t("memberDetailsBody"),
            }
          : role && {
              id: role.name,
              name: role.name,
              state: role.parent_role ?? "base",
              revision: role.revision,
              role: role.name,
              parentRole: role.parent_role,
              rolePermissions: role.permissions,
              title: t("roleDetails"),
              description: t("roleDetailsBody"),
            };

  if (!detail) notFound();
  const subjectKind =
    resource === "members"
      ? "employee"
      : resource === "teams"
        ? "team"
        : resource === "projects"
          ? "project"
          : null;
  const assignments = subjectKind
    ? await readCorporateCatalogAssignments(
        session,
        workspace.organization.organization_id,
        subjectKind,
        resourceId,
      )
    : null;
  const assignmentSummaries = assignments
    ? await mapPool(assignments.items, 6, (item) => readAssignedObjectSummary(item, session))
    : [];
  const assignmentCards: Record<string, OwnerCardItem> = Object.fromEntries(
    (assignments?.items ?? []).map((item, index) => {
      const summary = assignmentSummaries[index] ?? null;
      return [
        item.assignment_id,
        {
          ...assignmentCardItem(item),
          catalog_item: summary,
          latest_version: summary?.latest_version ?? item.version,
        },
      ];
    }),
  );

  const parentHref =
    resource === "roles"
      ? "/corporate/organization/admins"
      : `/corporate/${resource === "members" ? "employees" : resource}${directoryQuery ? `?${directoryQuery}` : ""}`;
  const backLabel =
    resource === "roles"
      ? h("backToAdmins")
      : resource === "members"
        ? h("backToEmployees")
        : resource === "teams"
          ? h("backToTeams")
          : h("backToProjects");
  let presentation =
    resource === "roles"
      ? null
      : await readCorporatePresentation(
          session,
          workspace.organization.organization_id,
          resource,
          resourceId,
          workspace.context.organization.authorization_revision,
        );
  if (presentation) {
    if (team) {
      const leadAccountIds = new Set(team.lead_account_ids);
      presentation.leads = team.members
        .filter(
          (item) =>
            leadAccountIds.has(item.account_id) ||
            item.role === "lead" ||
            item.role === "team_lead",
        )
        .map((item) => ({
          kind: "employee",
          id: item.account_id,
          name: item.display_name ?? h("employees"),
        }));
    }
    if (projectDetail) {
      presentation.technologies = (projectDetail.relations?.items ?? [])
        .filter((item) => item.state === "current")
        .flatMap((item) => {
          const relatedTechnology = projectDetail.technologies.find(
            (candidate) => candidate.technology_id === item.technology_id,
          );
          return relatedTechnology
            ? [
                {
                  kind: "technology" as const,
                  id: relatedTechnology.technology_id,
                  name: relatedTechnology.name,
                },
              ]
            : [];
        });
    }
    if (projectDetail?.projectTeams) {
      presentation.teams = projectDetail.projectTeams.items
        .filter((item) => item.state === "current")
        .flatMap((item) => {
          const relatedTeam = projectDetail.teams.find(
            (candidate) => candidate.team_id === item.team_id,
          );
          return relatedTeam
            ? [{ kind: "team" as const, id: relatedTeam.team_id, name: relatedTeam.name }]
            : [];
        });
      const owner = projectDetail.projectTeams.items.find(
        (item) => item.state === "current" && item.role === "owner",
      );
      const ownerTeam = projectDetail.teams.find((item) => item.team_id === owner?.team_id);
      presentation.owner = ownerTeam
        ? { kind: "team", id: ownerTeam.team_id, name: ownerTeam.name }
        : null;
    }
    if (member && employeeContent) {
      presentation = await assembleCorporateEmployeePresentation({
        presentation,
        sessionToken: session,
        organizationId: workspace.organization.organization_id,
        member,
        teams: workspace.context.teams,
        projects: workspace.context.projects,
        projectIds: workspace.projectMemberships?.items.map((item) => item.project_id) ?? [],
        content: employeeContent,
        includeTechnologies: true,
        unknownName: t("unknownEmployee"),
      });
    }
  }
  const displayDescription = presentation
    ? presentation.description
    : team?.description || detail.description;
  const csrfToken = (await readCsrfToken()) ?? "";
  const actionSet =
    resource === "teams"
      ? (team?.available_actions ?? [])
      : resource === "members"
        ? (member?.available_actions ?? workspace.context.capabilities)
        : resource === "projects"
          ? (project?.available_actions ?? workspace.context.capabilities)
          : workspace.context.capabilities;
  const canDelete = actionSet.includes(
    `${resource === "members" ? "member" : resource === "roles" ? "role" : resource.slice(0, -1)}.delete`,
  );
  return (
    <article className="mx-auto max-w-7xl space-y-8">
      <HistoryBackButton label={backLabel} fallback={parentHref} />
      <CorporateEntityDetail
        presentation={presentation}
        description={displayDescription}
        resource={resource === "roles" ? "teams" : resource}
        resourceId={resourceId}
        title={detail.name}
        adminMenu={
          canDelete ? (
            <LocalizedResourceDeleteMenuItem
              csrfToken={csrfToken}
              organizationId={workspace.context.organization.organization_id}
              authorizationRevision={workspace.context.organization.authorization_revision}
              resource={resource}
              resourceId={detail.id}
              revision={detail.revision}
            />
          ) : null
        }
        {...(detail.role || detail.state !== "active"
          ? { state: detail.role ?? detail.state }
          : {})}
      >
        {resource === "teams" && team ? (
          <>
            {team.members.length ? (
              <CorporateRelationSection
                title={h("employees")}
                resource="members"
                references={team.members.map((item) => ({
                  kind: "employee" as const,
                  id: item.account_id,
                  name: item.display_name ?? h("employees"),
                }))}
                labels={relationSectionLabels(h)}
                api={{ resource: "members", filters: { team_ids: [team.team_id] } }}
              />
            ) : null}
            {teamProjects.length ? (
              <CorporateRelationSection
                title={h("projects")}
                resource="projects"
                references={teamProjects.map((project) => ({
                  kind: "project" as const,
                  id: project.project_id,
                  name: project.name,
                }))}
                labels={relationSectionLabels(h)}
                api={{ resource: "projects", filters: { team_ids: [team.team_id] } }}
              />
            ) : null}
          </>
        ) : null}
        {member && employeeContent ? (
          <CorporateEmployeeDetail
            content={employeeContent}
            labels={corporateEmployeeDetailLabels(t)}
          />
        ) : null}
        {assignments && subjectKind && (
          <CorporateCatalogAssignments
            items={assignments.items}
            cards={assignmentCards}
            organizationId={workspace.organization.organization_id}
            subjectKind={subjectKind}
            subjectId={resourceId}
            authorizationRevision={workspace.organization.authorization_revision}
            csrfToken={csrfToken}
            canManage={
              resource === "teams"
                ? Boolean(team?.available_actions.includes("assignment.manage"))
                : workspace.context.capabilities.includes("catalog_object.assign")
            }
          />
        )}
      </CorporateEntityDetail>
    </article>
  );
}
