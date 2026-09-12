import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Badge } from "@/components/atoms/badge";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateTeamEditor } from "@/components/organisms/corporate-team-editor";
import { CorporateTeamMemberships } from "@/components/organisms/corporate-team-memberships";
import { CorporateResourceActions } from "@/components/organisms/corporate-resource-actions";
import { ApiError } from "@/lib/api/errors";
import { readCorporateWorkspace } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

type PageProps = {
  params: Promise<{ locale: string; resource: string; resourceId: string }>;
};

// eslint-disable-next-line complexity
export default async function CorporateResourcePage({ params }: PageProps) {
  const { locale, resource, resourceId } = await params;
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

  let workspace;
  try {
    workspace = await readCorporateWorkspace((await sessionCookieValue()) ?? "");
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }
  if (!workspace) notFound();

  const project = workspace.context.projects.find((item) => item.project_id === resourceId);
  const team = workspace.context.teams.find((item) => item.team_id === resourceId);
  const member = workspace.members?.items.find((item) => item.account_id === resourceId);
  const role = workspace.roles?.items.find((item) => item.name === resourceId);
  const detail =
    resource === "projects"
      ? project && {
          id: project.project_id,
          name: project.name,
          state: project.state,
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
              role: member.role,
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

  return (
    <article className="mx-auto max-w-5xl space-y-6">
      <HistoryBackButton label={t("backToWorkspace")} fallback="/corporate" />
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant="outline">{detail.state}</Badge>
          {detail.role ? <Badge variant="secondary">{detail.role}</Badge> : null}
        </div>
        <h1 className="text-3xl font-medium tracking-tight">{detail.name}</h1>
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
        </>
      ) : null}
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
      <details className="border-border border-t pt-4">
        <summary className="text-muted-foreground cursor-pointer text-sm">
          {t("viewDetails")}
        </summary>
        <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-muted-foreground">{t("id")}</dt>
            <dd className="mt-1 font-mono text-xs break-all">{detail.id}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{t("state")}</dt>
            <dd className="mt-1">{detail.state}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{t("revision")}</dt>
            <dd className="mt-1">{detail.revision}</dd>
          </div>
        </dl>
      </details>
      {resource !== "teams" && (
        <CorporateResourceActions
          csrfToken={(await readCsrfToken()) ?? ""}
          organizationId={workspace.context.organization.organization_id}
          authorizationRevision={workspace.context.organization.authorization_revision}
          resource={resource}
          resourceId={detail.id}
          name={detail.name}
          {...(detail.role === undefined ? {} : { role: detail.role })}
          {...("parentRole" in detail ? { parentRole: detail.parentRole } : {})}
          {...("rolePermissions" in detail ? { rolePermissions: detail.rolePermissions } : {})}
          state={detail.state}
          revision={detail.revision}
          roles={workspace.roles?.items ?? []}
          permissions={workspace.context.capabilities}
          labels={{
            title: t("actions"),
            name: t("name"),
            role: t("organizationRole"),
            parentRole: t("parentRole"),
            permissions: t("permissions"),
            state: t("state"),
            update: t("update"),
            saving: t("saving"),
            saved: t("saved"),
            delete: t("delete"),
            deleting: t("deleting"),
            confirmDelete: t("confirmDelete"),
            staff: t("staff"),
            lead: t("lead"),
            superadmin: t("superadmin"),
            active: t("active"),
            suspended: t("suspended"),
            archived: t("archived"),
          }}
        />
      )}
    </article>
  );
}
