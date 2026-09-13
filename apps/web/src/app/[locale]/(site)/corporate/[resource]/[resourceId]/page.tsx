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
import { CorporateProjectMemberships } from "@/components/organisms/corporate-project-memberships";
import { CorporateMemberProfile } from "@/components/organisms/corporate-member-profile";
import { CorporateEmployeeTechnologies } from "@/components/organisms/corporate-employee-technologies";
import { ProjectTechnologyEditor } from "@/components/organisms/project-technology-editor";
import { ProjectTeamEditor } from "@/components/organisms/project-team-editor";
import { ProjectLifecycleControls } from "@/components/organisms/corporate-governance-controls";
import { ApiError } from "@/lib/api/errors";
import {
  readCorporateResource,
  readCorporateCatalogAssignments,
  readEmployeeTechnologies,
} from "@/lib/api/corporate";
import { readTechnologyRegistry } from "@/lib/api/technology";
import { readProjectTechnologyDetail, readTeamProjects } from "@/lib/api/technology";
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
    member && workspace.context.capabilities.includes("technology.list")
      ? await Promise.all([
          readEmployeeTechnologies(
            session,
            workspace.organization.organization_id,
            member.account_id,
          ),
          readTechnologyRegistry(session, workspace.organization.organization_id),
        ])
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
              name: member.display_name ?? member.account_id,
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
  return (
    <article className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <HistoryBackButton label={h("historyBack")} fallback={parentHref} />
        <Link
          href={parentHref}
          className="text-muted-foreground text-sm underline underline-offset-4"
        >
          {resource === "roles" ? h("admins") : h("back")}
        </Link>
      </div>
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant="outline">{detail.state}</Badge>
          {detail.role ? <Badge variant="secondary">{detail.role}</Badge> : null}
        </div>
        <h1 className="text-3xl font-medium tracking-tight [overflow-wrap:anywhere]">
          {detail.name}
        </h1>
        <p className="text-muted-foreground max-w-prose">
          {team ? team.description || t("noDescription") : detail.description}
        </p>
      </header>

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
            title: h("technologies"),
            empty: t("noEmployeeTechnologies"),
            assign: tc("assign"),
            remove: tc("remove"),
            technology: t("technology"),
          }}
        />
      )}
      {resource === "members" && member ? (
        <CorporateTeamMemberships
          employee={member}
          teams={workspace.context.teams}
          members={workspace.members?.items ?? []}
          organizationId={workspace.context.organization.organization_id}
          csrfToken={(await readCsrfToken()) ?? ""}
          canManage={workspace.context.capabilities.includes("member.manage")}
        />
      ) : null}
      {projectDetail && (
        <ProjectTechnologyPanel detail={projectDetail} csrfToken={(await readCsrfToken()) ?? ""} />
      )}
      {member && workspace.projectMemberships && (
        <CorporateProjectMemberships
          organizationId={workspace.organization.organization_id}
          authorizationRevision={workspace.organization.authorization_revision}
          csrfToken={(await readCsrfToken()) ?? ""}
          accountId={member.account_id}
          options={workspace.context.projects.map((item) => ({
            id: item.project_id,
            name: item.name,
          }))}
          assigned={workspace.projectMemberships.items.map((item) => ({
            id: item.project_id,
            name: item.name,
          }))}
          canManage={workspace.context.capabilities.includes("member.manage")}
        />
      )}
      {project && workspace.projectMembers && (
        <CorporateProjectMemberships
          organizationId={workspace.organization.organization_id}
          authorizationRevision={workspace.organization.authorization_revision}
          csrfToken={(await readCsrfToken()) ?? ""}
          projectId={project.project_id}
          options={(workspace.members?.items ?? []).map((item) => ({
            id: item.account_id,
            name: item.display_name ?? item.account_id,
          }))}
          assigned={workspace.projectMembers.items.map((item) => ({
            id: item.account_id,
            name: item.display_name ?? item.account_id,
          }))}
          canManage={workspace.context.capabilities.includes("member.manage")}
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
  const t = await getTranslations("technology");
  return (
    <>
      {detail.projectTeams && (
        <ProjectTeamEditor
          projectId={detail.project.project_id}
          organizationId={detail.project.organization_id}
          authorizationRevision={detail.permissions.authorization_revision}
          csrfToken={csrfToken}
          capabilities={detail.permissions.capabilities}
          teams={detail.teams}
          relations={detail.projectTeams.items}
        />
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
      {detail.relations && (
        <section className="space-y-3" aria-label={t("manualUsage")}>
          <h2 className="text-xl font-medium">{t("manualUsage")}</h2>
          <ul className="divide-border divide-y">
            {detail.relations.items
              .filter((relation) => relation.state === "current")
              .map((relation) => (
                <li key={relation.relation_id} className="space-y-2 py-3">
                  <Link
                    href={`/corporate/technologies/${relation.technology_id}`}
                    className="font-medium underline underline-offset-4"
                  >
                    {detail.technologies.find(
                      (technology) => technology.technology_id === relation.technology_id,
                    )?.name ?? t("values.unknown")}
                  </Link>
                  <ul>
                    {relation.facts.map((fact) => (
                      <li key={fact.context} className="text-sm">
                        {t(`values.${fact.context}`)} · {fact.version ?? t("values.unknown")}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
          </ul>
        </section>
      )}
    </>
  );
}
