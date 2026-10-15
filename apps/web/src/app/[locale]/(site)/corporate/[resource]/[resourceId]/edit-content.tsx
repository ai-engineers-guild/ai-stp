import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { RouteDialog } from "@/components/molecules/route-dialog";
import { CorporateMemberRouteDialog } from "@/components/organisms/corporate-member-route-dialog";
import { CorporateResourceActions } from "@/components/organisms/corporate-resource-actions";
import { CorporateProjectRepository } from "@/components/organisms/corporate-project-repository";
import { readCorporateResource, readCorporateWorkspace } from "@/lib/api/corporate";
import { readProjectTechnologyDetail } from "@/lib/api/technology";
import { loadEntityActionMenus } from "@/actions/entity-actions";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export async function CorporateEntityEditPage({
  locale,
  resource,
  resourceId,
}: {
  locale: string;
  resource: string;
  resourceId: string;
}) {
  if (!["employees", "teams", "projects"].includes(resource)) notFound();
  await requireSession(locale, `/${locale}/corporate/${resource}/${resourceId}/edit`);
  const token = (await sessionCookieValue()) ?? "";
  const normalized = resource === "employees" ? "members" : (resource as "teams" | "projects");
  const workspace = await readCorporateResource(token, normalized, resourceId);
  if (!workspace) notFound();
  const organizationId = workspace.organization.organization_id;
  const { menus } = await loadEntityActionMenus([
    {
      kind: normalized === "members" ? "member" : normalized === "teams" ? "team" : "project",
      id: resourceId,
      organization_id: organizationId,
    },
  ]);
  if (!menus.items[0]?.actions.some((action) => action.id === "edit")) notFound();
  const csrfToken = (await readCsrfToken()) ?? "";
  if (normalized === "members") {
    if (!workspace.member) notFound();
    const full = await readCorporateWorkspace(token, false);
    return (
      <CorporateMemberRouteDialog
        member={workspace.member}
        context={{
          ...workspace.context,
          capabilities: [
            ...new Set([...workspace.context.capabilities, ...workspace.member.available_actions]),
          ],
        }}
        roles={workspace.roles?.items ?? []}
        jobTitles={full?.jobTitles?.items ?? []}
        csrfToken={csrfToken}
      />
    );
  }
  const detail =
    normalized === "projects"
      ? await readProjectTechnologyDetail(token, organizationId, resourceId)
      : null;
  const entity = detail?.project ?? workspace.team;
  if (!entity) notFound();
  const c = await getTranslations("corporate");
  const labels = {
    title: c("actions"),
    name: c("name"),
    role: c("role"),
    permissions: c("permissions"),
    state: c("state"),
    update: c("update"),
    saving: c("saving"),
    saved: c("saved"),
    delete: c("delete"),
    deleting: c("deleting"),
    confirmDelete: c("confirmDelete"),
    staff: c("staff"),
    lead: c("lead"),
    superadmin: c("superadmin"),
    active: c("active"),
    suspended: c("suspended"),
    archived: c("archived"),
  };
  return (
    <RouteDialog title={c("edit")} fallback={`/corporate/${resource}/${resourceId}`}>
      <CorporateResourceActions
        initiallyEditing
        closeOnSave
        resource={normalized}
        resourceId={resourceId}
        name={entity.name}
        description={workspace.team?.description ?? ""}
        state={entity.state}
        revision={entity.revision}
        organizationId={organizationId}
        authorizationRevision={workspace.organization.authorization_revision}
        csrfToken={csrfToken}
        permissions={workspace.context.capabilities}
        labels={labels}
      />
      {detail ? (
        <CorporateProjectRepository
          project={detail.project}
          organizationId={organizationId}
          authorizationRevision={workspace.organization.authorization_revision}
          csrfToken={csrfToken}
          canManage
        />
      ) : null}
    </RouteDialog>
  );
}
