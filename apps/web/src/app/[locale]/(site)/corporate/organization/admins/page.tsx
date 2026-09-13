import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateAdminPanel } from "@/components/organisms/corporate-admin-panel";
import { CorporateAccessPanel } from "@/components/organisms/corporate-access-panel";
import { ApiError } from "@/lib/api/errors";
import { readCorporateContext, readCorporateWorkspace } from "@/lib/api/corporate";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type PageProps = { params: Promise<{ locale: string }> };

// eslint-disable-next-line max-lines-per-function, complexity
export default async function CorporateAdministrationPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins`);
  const t = await getTranslations("corporate");
  const tc = await getTranslations("common");
  const technology = await getTranslations("technology");

  let workspace;
  let forbidden = false;
  try {
    const session = (await sessionCookieValue()) ?? "";
    const context = await readCorporateContext(session);
    forbidden = Boolean(context && !canViewCorporateAdministration(context.capabilities));
    if (!forbidden) workspace = await readCorporateWorkspace(session, false);
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }
  if (forbidden)
    return (
      <StatePanel kind="error" title={t("administration")} description={technology("forbidden")} />
    );
  if (!workspace) {
    return <StatePanel kind="empty" title={t("emptyTitle")} description={t("emptyBody")} />;
  }

  const { context, members, roles, bindings, servicePrincipals } = workspace;
  const canManageRoles = context.capabilities.includes("role.create");

  return (
    <div className="min-w-0 space-y-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{t("administration")}</h1>
          <Badge variant="secondary">{context.member.role}</Badge>
        </div>
        <p className="text-muted-foreground">{t("subtitle")}</p>
      </header>

      {(context.capabilities.includes("technology.list") ||
        context.capabilities.includes("technology.create") ||
        context.capabilities.includes("category.create")) && (
        <Link
          href="/corporate/technologies"
          className="inline-flex min-h-11 items-center underline underline-offset-4"
        >
          {technology("registry")}
        </Link>
      )}
      {context.capabilities.includes("landscape.read") && (
        <Link
          href="/corporate/technology-landscape"
          className="inline-flex min-h-11 items-center underline underline-offset-4"
        >
          {technology("title")}
        </Link>
      )}
      {context.capabilities.includes("landscape.manage") && (
        <Link
          href="/corporate/organization/admins/settings"
          className="inline-flex min-h-11 items-center underline underline-offset-4"
        >
          {technology("activityPolicy")}
        </Link>
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        {roles ? (
          <CorporateList
            title={t("roles")}
            empty={t("noRoles")}
            items={roles.items.map((item) => ({
              id: item.name,
              name: item.name,
              state: item.parent_role ?? "base",
              revision: item.revision,
            }))}
            kind="roles"
            openLabel={t("open")}
          />
        ) : null}
      </div>

      {canManageRoles && (
        <details className="border-border border-t pt-4">
          <summary className="cursor-pointer font-medium">{t("administration")}</summary>
          <div className="mt-4">
            <CorporateAdminPanel
              csrfToken={(await readCsrfToken()) ?? ""}
              organizationId={context.organization.organization_id}
              authorizationRevision={context.organization.authorization_revision}
              roles={roles?.items ?? []}
              permissions={context.capabilities.filter((permission) =>
                permission.startsWith("role."),
              )}
              labels={{
                title: t("administration"),
                description: t("administrationBody"),
                members: t("members"),
                projects: t("projects"),
                teams: t("teams"),
                roles: t("roles"),
                displayName: t("displayName"),
                email: t("email"),
                name: t("name"),
                role: t("organizationRole"),
                parentRole: t("parentRole"),
                permissions: t("permissions"),
                create: t("create"),
                creating: t("creating"),
                saved: t("saved"),
                failed: t("failed"),
                staff: t("staff"),
                lead: t("lead"),
              }}
            />
          </div>
        </details>
      )}
      {(context.capabilities.includes("member.manage") ||
        context.capabilities.includes("binding.create") ||
        context.capabilities.includes("service_principal.manage")) && (
        <details className="border-border border-t pt-4">
          <summary className="cursor-pointer font-medium">{t("accessAdministration")}</summary>
          <div className="mt-4">
            <CorporateAccessPanel
              csrfToken={(await readCsrfToken()) ?? ""}
              organizationId={context.organization.organization_id}
              authorizationRevision={context.organization.authorization_revision}
              members={members?.items ?? []}
              projects={context.projects}
              teams={context.teams}
              roles={roles?.items ?? []}
              bindings={bindings?.items ?? []}
              servicePrincipals={servicePrincipals?.items ?? []}
              permissions={context.capabilities}
              labels={{
                title: t("accessAdministration"),
                assignments: t("assignments"),
                bindings: t("bindings"),
                servicePrincipals: t("servicePrincipals"),
                member: t("member"),
                team: t("team"),
                project: t("project"),
                role: t("role"),
                state: t("state"),
                scope: t("scope"),
                organization: t("organization"),
                operation: t("operation"),
                assign: t("assign"),
                remove: t("remove"),
                create: t("create"),
                creating: t("creating"),
                update: t("update"),
                saving: t("saving"),
                delete: t("delete"),
                deleting: t("deleting"),
                activate: t("active"),
                suspend: t("suspended"),
                staff: t("staff"),
                lead: t("lead"),
                superadmin: t("superadmin"),
                noBindings: t("noBindings"),
                noServicePrincipals: t("noServicePrincipals"),
                confirmDelete: t("confirmDelete"),
                targetRequired: t("targetRequired"),
                saved: t("saved"),
                failed: t("failed"),
              }}
            />
          </div>
        </details>
      )}
      {context.capabilities.includes("audit.list") ? (
        <Link
          href="/corporate/organization/admins/audit"
          className="inline-flex min-h-11 items-center underline underline-offset-4"
        >
          {t("auditJournal")}
        </Link>
      ) : null}
    </div>
  );
}

function CorporateList({
  title,
  empty,
  items,
  kind,
  openLabel,
}: {
  title: string;
  empty: string;
  items: ReadonlyArray<{ id: string; name: string; state: string; revision: number }>;
  kind: "projects" | "teams" | "roles";
  openLabel: string;
}) {
  return (
    <section className="border-border bg-card rounded-lg border p-5 shadow-sm sm:p-6">
      <h2 className="text-xl font-medium">{title}</h2>
      {items.length ? (
        <ul className="mt-4 space-y-2">
          {items.map((item) => (
            <li key={item.id} className="border-border rounded border">
              <Link
                href={`/corporate/${kind}/${encodeURIComponent(item.id)}`}
                className="focus-visible:ring-ring group flex min-h-14 items-center justify-between gap-3 rounded p-3 outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
              >
                <span className="min-w-0 truncate">{item.name}</span>
                <span className="text-muted-foreground flex shrink-0 items-center gap-2 text-sm">
                  {item.state}
                  <span className="sr-only">{openLabel}</span>
                  <Icon
                    name="chevronRight"
                    size="sm"
                    className="transition-transform group-hover:translate-x-0.5"
                  />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground mt-4 text-sm">{empty}</p>
      )}
    </section>
  );
}
