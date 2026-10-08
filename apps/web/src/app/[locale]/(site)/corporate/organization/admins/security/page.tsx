import { getTranslations, setRequestLocale } from "next-intl/server";
import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateServicePrincipalsPanel } from "@/components/organisms/corporate-service-principals-panel";
import { CorporateMembershipPolicyControls } from "@/components/organisms/corporate-membership-policy-controls";
import { readCorporateMembershipPolicy } from "@/lib/api/corporate-invitations";
import { readCorporateContext, readCorporateWorkspace } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function CorporateSecurityPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/security`);
  const session = (await sessionCookieValue()) ?? "";
  const hub = await getTranslations("hub");
  const technology = await getTranslations("technology");
  const corporate = await getTranslations("corporate");
  const context = await readCorporateContext(session);
  if (!context)
    return <StatePanel kind="empty" title={hub("security")} description={hub("empty")} />;
  const canReadPrincipals = context.capabilities.includes("service_principal.list");
  const canManageDomains = context.capabilities.includes("organization.manage");
  if (!canReadPrincipals && !canManageDomains)
    return (
      <StatePanel kind="error" title={hub("security")} description={technology("forbidden")} />
    );
  const organizationId = context.organization.organization_id;
  const [workspace, policy] = await Promise.all([
    canReadPrincipals ? readCorporateWorkspace(session, false) : Promise.resolve(null),
    canManageDomains
      ? readCorporateMembershipPolicy(session, organizationId)
      : Promise.resolve(null),
  ]);
  const authority = {
    organizationId,
    authorizationRevision: context.organization.authorization_revision,
    csrfToken: (await readCsrfToken()) ?? "",
  };
  return (
    <div className="min-w-0 space-y-6">
      <h1 className="text-3xl font-medium tracking-tight">{hub("security")}</h1>
      {policy ? (
        <CorporateMembershipPolicyControls
          {...authority}
          allowedDomains={policy.allowed_email_domains}
        />
      ) : null}
      {workspace?.servicePrincipals ? (
        <CorporateServicePrincipalsPanel
          csrfToken={authority.csrfToken}
          organizationId={organizationId}
          authorizationRevision={context.organization.authorization_revision}
          roles={workspace.roles?.items ?? []}
          servicePrincipals={workspace.servicePrincipals.items}
          teams={context.teams}
          projects={context.projects}
          capabilities={context.capabilities}
          labels={{
            title: corporate("servicePrincipals"),
            role: corporate("role"),
            scope: corporate("scope"),
            organization: corporate("organization"),
            team: corporate("team"),
            project: corporate("project"),
            create: corporate("create"),
            creating: corporate("creating"),
            activate: corporate("activate"),
            suspend: corporate("suspend"),
            delete: corporate("delete"),
            deleting: corporate("deleting"),
            confirmDelete: corporate("confirmDelete"),
            noServicePrincipals: corporate("noServicePrincipals"),
            saved: corporate("saved"),
            failed: corporate("failed"),
          }}
        />
      ) : null}
    </div>
  );
}
