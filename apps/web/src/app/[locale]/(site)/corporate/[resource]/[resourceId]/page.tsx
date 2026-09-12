import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Badge } from "@/components/atoms/badge";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
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
    <article className="mx-auto max-w-3xl space-y-6">
      <HistoryBackButton label={t("backToWorkspace")} fallback="/corporate" />
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant="outline">{detail.state}</Badge>
          {detail.role ? <Badge variant="secondary">{detail.role}</Badge> : null}
        </div>
        <h1 className="text-3xl font-medium tracking-tight">{detail.name}</h1>
        <p className="text-muted-foreground">{detail.description}</p>
      </header>

      <section className="border-border bg-card space-y-4 rounded-lg border p-5 shadow-sm sm:p-6">
        <h2 className="text-xl font-medium">{detail.title}</h2>
        <dl className="grid gap-4 text-sm sm:grid-cols-3">
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
      </section>
      {resource === "teams" && team ? (
        <section className="border-border bg-card space-y-4 rounded-lg border p-5">
          <h2 className="text-xl font-medium">{t("members")}</h2>
          <ul className="space-y-2">
            {team.members.map((item) => (
              <li key={item.account_id} className="flex flex-wrap items-center gap-3">
                <span>{item.display_name ?? item.account_id}</span>
                <Badge variant="outline">{item.state}</Badge>
                <Badge variant="secondary">
                  {team.lead_account_ids.includes(item.account_id) ? t("lead") : t("staff")}
                </Badge>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
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
        permissions={workspace.context.capabilities}
        labels={{
          title: t("actions"),
          name: t("name"),
          role: t("role"),
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
    </article>
  );
}
