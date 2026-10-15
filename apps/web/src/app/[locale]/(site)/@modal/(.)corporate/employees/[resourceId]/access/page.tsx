import { notFound } from "next/navigation";
import { CorporateGrantRouteDialog } from "@/components/organisms/corporate-member-route-dialog";
import {
  readCorporateWorkspace,
  readCorporateMemberAccess,
  readCorporateCatalogScopeOptions,
  readCorporateCategoryScopeOptions,
  readCorporateScopeTechnologies,
} from "@/lib/api/corporate";
import { apiRequest } from "@/lib/api/http";
import type { CorporatePermissionMatrix } from "@/lib/api/generated/types.gen";
import { loadEntityActionMenus } from "@/actions/entity-actions";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
export default async function GrantModal({
  params,
}: {
  params: Promise<{ locale: string; resourceId: string }>;
}) {
  const { locale, resourceId: employee } = await params;
  await requireSession(locale, `/${locale}/corporate/admin/employee-access`);
  if (!employee) notFound();
  const token = (await sessionCookieValue()) ?? "";
  const [workspace, access] = await Promise.all([
    readCorporateWorkspace(token, false),
    readCorporateMemberAccess(token, employee),
  ]);
  if (!workspace || !access) notFound();
  const org = workspace.organization.organization_id;
  const { menus } = await loadEntityActionMenus([
    { kind: "member", id: employee, organization_id: org },
  ]);
  if (!menus.items[0]?.actions.some((action) => action.id === "manage_access")) notFound();
  const caps = workspace.context.capabilities;
  const [matrix, technologies, catalog, categories] = await Promise.all([
    caps.includes("role.read")
      ? apiRequest<CorporatePermissionMatrix>(
          `/v1/corporate/organizations/${org}/permissions/matrix`,
          { sessionToken: token },
        )
      : null,
    readCorporateScopeTechnologies(token, org, caps),
    readCorporateCatalogScopeOptions(token, org, caps),
    readCorporateCategoryScopeOptions(token, org, caps),
  ]);
  const context = workspace.context;
  return (
    <CorporateGrantRouteDialog
      csrfToken={(await readCsrfToken()) ?? ""}
      organizationId={org}
      authorizationRevision={workspace.context.organization.authorization_revision}
      members={workspace.members?.items ?? [access.member]}
      initialMemberIds={[employee]}
      roles={workspace.roles?.items ?? []}
      grantableRoleNames={access.delegation?.grantable_roles.map((role) => role.name) ?? null}
      teams={context.teams}
      projects={context.projects}
      capabilities={caps}
      definitions={matrix?.definitions ?? []}
      scopeOptions={[
        ...technologies.map((item) => ({ value: `technology:${item.id}`, label: item.name })),
        ...catalog,
        ...categories,
      ]}
    />
  );
}
