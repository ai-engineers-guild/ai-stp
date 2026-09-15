/* eslint-disable max-lines -- this route intentionally owns all corporate resource actions. */
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Badge } from "@/components/atoms/badge";
import { Link } from "@/lib/i18n/navigation";
import { StatePanel } from "@/components/molecules/state-panel";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { CorporateTeamEditor } from "@/components/organisms/corporate-team-editor";
import { CorporateTeamMemberships } from "@/components/organisms/corporate-team-memberships";
import { LocalizedResourceActions } from "@/components/organisms/localized-corporate-resource-actions";
import { CorporateCatalogAssignments } from "@/components/organisms/corporate-catalog-assignments";
import { CorporateMemberProfile } from "@/components/organisms/corporate-member-profile";
import { CorporateEmployeeTechnologies } from "@/components/organisms/corporate-employee-technologies";
import {
  CorporateEmployeeDetail,
  corporateEmployeeDetailLabels,
} from "@/components/organisms/corporate-employee-detail";
import { CorporateEntityDetail } from "@/components/organisms/corporate-entity-detail";
import { readCorporatePresentation } from "@/lib/api/corporate-detail";
import {
  assembleCorporateEmployeePresentation,
  readCorporateEmployeeContent,
} from "@/lib/api/corporate-employee";
import { ProjectTechnologyEditor } from "@/components/organisms/project-technology-editor";
import { ProjectTeamEditor } from "@/components/organisms/project-team-editor";
import { ProjectLifecycleControls } from "@/components/organisms/corporate-governance-controls";
import { ApiError } from "@/lib/api/errors";
import {
  readCorporateResource,
  readCorporateCatalogAssignments,
  readEmployeeTechnologies,
} from "@/lib/api/corporate";
import {
  readProjectTechnologyDetail,
  readTechnologyRegistry,
  readTeamProjects,
} from "@/lib/api/technology";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

type PageProps = {
  params: Promise<{ locale: string; resource: string; resourceId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

// eslint-disable-next-line complexity, max-lines-per-function
export default async function CorporateResourcePage({ params, searchParams }: PageProps) {
  const { locale, resource, resourceId } = await params;
  const filters = await searchParams;
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
  const technology = await getTranslations("technology");
  const session = (await sessionCookieValue()) ?? "";

  let workspace;
  try {
    workspace = await readCorporateResource(session, resource, resourceId);
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }
  if (!workspace) notFound();

  const projectDetail =
    resource === "projects"
      ? await readProjectTechnologyDetail(
          session,
          workspace.organization.organization_id,
          resourceId,
        )
      : null;
  const project = projectDetail?.project;
  const team = workspace.team;
  const teamProjects = team
    ? await readTeamProjects(session, workspace.organization.organization_id, team.team_id)
    : null;
  const member = workspace.member;
  const competenceData =
    member &&
    workspace.context.capabilities.includes("technology.list") &&
    workspace.context.capabilities.includes("member.manage")
      ? await Promise.all([
          readEmployeeTechnologies(
            session,
            workspace.organization.organization_id,
            member.account_id,
          ),
          readTechnologyRegistry(session, workspace.organization.organization_id),
        ])
      : null;
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

  const parentHref =
    resource === "roles"
      ? "/corporate/organization/admins"
      : `/corporate/${resource}${directoryQuery ? `?${directoryQuery}` : ""}`;
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
      presentation.leads = team.members
        .filter((item) => item.role === "lead")
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
        content: employeeContent,
        includeTechnologies: true,
        unknownName: t("unknownEmployee"),
      });
    }
  }
  const displayDescription = presentation
    ? presentation.description
    : team?.description || detail.description;
  return (
    <article className="mx-auto max-w-7xl space-y-8">
      <HistoryBackButton label={backLabel} fallback={parentHref} />
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant="outline">{detail.state}</Badge>
          {detail.role ? <Badge variant="secondary">{detail.role}</Badge> : null}
        </div>
        <h1 className="text-3xl font-medium tracking-tight [overflow-wrap:anywhere]">
          {presentation?.name ?? detail.name}
        </h1>
      </header>
      <CorporateEntityDetail
        presentation={presentation}
        description={displayDescription}
        organizationId={workspace.organization.organization_id}
        resource={resource === "roles" ? "teams" : resource}
        resourceId={resourceId}
        csrfToken={(await readCsrfToken()) ?? ""}
      >
        {resource === "teams" && team ? (
          <>
            <CorporateTeamEditor
              team={team}
              organizationId={workspace.context.organization.organization_id}
              authorizationRevision={workspace.context.organization.authorization_revision}
              csrfToken={(await readCsrfToken()) ?? ""}
              canManage={workspace.context.capabilities.includes("team.update")}
            />
            <CorporateTeamMemberships
              team={team}
              teams={workspace.context.teams}
              members={workspace.members?.items ?? []}
              organizationId={workspace.context.organization.organization_id}
              csrfToken={(await readCsrfToken()) ?? ""}
              canManage={workspace.context.capabilities.includes("member.manage")}
            />
            {teamProjects && (
              <section className="space-y-3">
                <h2 className="text-xl font-medium">{h("projects")}</h2>
                <ul className="divide-border divide-y">
                  {teamProjects.relations.items
                    .filter((item) => item.state === "current")
                    .map((item) => (
                      <li
                        key={item.relation_id}
                        className="flex flex-wrap items-center justify-between gap-3 py-3"
                      >
                        <Link
                          href={`/corporate/projects/${item.project_id}`}
                          className="inline-flex min-h-11 items-center underline underline-offset-4"
                        >
                          {teamProjects.projects?.items.find(
                            (project) => project.project_id === item.project_id,
                          )?.name ?? h("projects")}
                        </Link>
                        <span className="text-muted-foreground text-sm">{h(item.role)}</span>
                      </li>
                    ))}
                </ul>
                {!teamProjects.relations.items.some((item) => item.state === "current") && (
                  <p className="text-muted-foreground text-sm">{h("empty")}</p>
                )}
              </section>
            )}
          </>
        ) : null}
        {member && workspace.context.capabilities.includes("member.update") && (
          <CorporateMemberProfile
            member={member}
            organizationId={workspace.organization.organization_id}
            authorizationRevision={workspace.context.organization.authorization_revision}
            csrfToken={(await readCsrfToken()) ?? ""}
          />
        )}
        {member && employeeContent ? (
          <CorporateEmployeeDetail
            content={employeeContent}
            leadTeams={(presentation?.leads ?? [])
              .filter((ref) => ref.kind === "team")
              .map((ref) => ({ id: ref.id, name: ref.name }))}
            labels={corporateEmployeeDetailLabels(t)}
          />
        ) : null}
        {member && competenceData?.[0] && competenceData[1].technologies && (
          <CorporateEmployeeTechnologies
            employee={member}
            assignments={competenceData[0]}
            technologies={competenceData[1].technologies.items}
            organizationId={workspace.organization.organization_id}
            authorizationRevision={workspace.organization.authorization_revision}
            csrfToken={(await readCsrfToken()) ?? ""}
            canManage={workspace.context.capabilities.includes("member.manage")}
            labels={{
              edit: tc("edit"),
              empty: technology("noEmployeeTechnologies"),
              assign: t("assign"),
              remove: t("remove"),
              technology: technology("technology"),
            }}
          />
        )}
        {projectDetail && (
          <ProjectTechnologyPanel
            detail={projectDetail}
            csrfToken={(await readCsrfToken()) ?? ""}
          />
        )}
        {assignments && subjectKind && (
          <CorporateCatalogAssignments
            items={assignments.items}
            organizationId={workspace.organization.organization_id}
            subjectKind={subjectKind}
            subjectId={resourceId}
            authorizationRevision={workspace.organization.authorization_revision}
            csrfToken={(await readCsrfToken()) ?? ""}
            canManage={workspace.context.capabilities.includes(
              subjectKind === "employee" ? "member.manage" : `${subjectKind}.update`,
            )}
          />
        )}
        {member &&
          workspace.context.capabilities.some((capability) =>
            ["member.update", "member.delete"].includes(capability),
          ) && (
            <Link
              href={`/corporate/organization/admins/members/${member.account_id}`}
              className="inline-flex min-h-11 items-center underline underline-offset-4"
            >
              {t("accessAdministration")}
            </Link>
          )}
        {resource !== "teams" && resource !== "members" && project?.lifecycle !== "deleted" && (
          <LocalizedResourceActions
            csrfToken={(await readCsrfToken()) ?? ""}
            organizationId={workspace.context.organization.organization_id}
            authorizationRevision={workspace.context.organization.authorization_revision}
            resource={resource}
            resourceId={detail.id}
            name={detail.name}
            {...(detail.role === undefined ? {} : { role: detail.role })}
            {...("parentRole" in detail ? { parentRole: detail.parentRole } : {})}
            {...("rolePermissions" in detail ? { rolePermissions: detail.rolePermissions } : {})}
            state={project?.state ?? detail.state}
            revision={detail.revision}
            permissions={projectDetail?.permissions.capabilities ?? workspace.context.capabilities}
          />
        )}
      </CorporateEntityDetail>
    </article>
  );
}

async function ProjectTechnologyPanel({
  detail,
  csrfToken,
}: {
  detail: NonNullable<Awaited<ReturnType<typeof readProjectTechnologyDetail>>>;
  csrfToken: string;
}) {
  const h = await getTranslations("hub");
  const canManageTeams = detail.permissions.capabilities.some((capability) =>
    ["project_team.create", "project_team.update", "project_team.delete"].includes(capability),
  );
  return (
    <>
      {detail.projectTeams && canManageTeams && (
        <details>
          <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
            {h("edit")}
          </summary>
          <div className="pt-3">
            <ProjectTeamEditor
              projectId={detail.project.project_id}
              organizationId={detail.project.organization_id}
              authorizationRevision={detail.permissions.authorization_revision}
              csrfToken={csrfToken}
              capabilities={detail.permissions.capabilities}
              teams={detail.teams}
              relations={detail.projectTeams.items}
            />
          </div>
        </details>
      )}
      {detail.permissions.capabilities.includes("project.update") && (
        <>
          <ProjectLifecycleControls
            project={detail.project}
            organizationId={detail.project.organization_id}
            authorizationRevision={detail.permissions.authorization_revision}
            csrfToken={csrfToken}
          />
        </>
      )}
      {detail.permissions.capabilities.some((capability) =>
        [
          "project_technology.create",
          "project_technology.update",
          "project_technology.delete",
        ].includes(capability),
      ) && (
        <ProjectTechnologyEditor
          organizationId={detail.project.organization_id}
          projectId={detail.project.project_id}
          authorizationRevision={detail.permissions.authorization_revision}
          csrfToken={csrfToken}
          capabilities={detail.permissions.capabilities}
          usages={detail.relations?.items ?? []}
          technologies={detail.technologies}
        />
      )}
    </>
  );
}
