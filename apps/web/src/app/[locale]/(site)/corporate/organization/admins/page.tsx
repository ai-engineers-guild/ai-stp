import { getTranslations, setRequestLocale } from "next-intl/server";
import { NavigationTabs } from "@/components/molecules/navigation-tabs";
import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateInvitationsPanel } from "@/components/organisms/corporate-invitations-panel";
import { isOutstandingInvitation } from "@/lib/corporate-invitation-state";
import { CorporateMembersDirectory } from "@/components/organisms/corporate-members-directory";
import { apiRequest } from "@/lib/api/http";
import type { CorporateDelegationView } from "@/lib/api/generated/types.gen";
import { ApiError } from "@/lib/api/errors";
import { readCorporateContext, readCorporateWorkspace } from "@/lib/api/corporate";
import { listCorporateInvitations } from "@/lib/api/corporate-invitations";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";
import { Icon, type IconName } from "@/theme";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

async function loadAdminData() {
  const session = (await sessionCookieValue()) ?? "";
  const context = await readCorporateContext(session);
  if (context && !canViewCorporateAdministration(context.capabilities))
    return { status: "forbidden" } as const;
  const workspace = await readCorporateWorkspace(session, false);
  if (!workspace) return { status: "empty" } as const;
  const invitations = workspace.context.capabilities.includes("member.invite")
    ? await listCorporateInvitations(session, workspace.context.organization.organization_id).catch(
        () => null,
      )
    : null;
  const delegation = workspace.context.capabilities.includes("member.invite")
    ? await apiRequest<CorporateDelegationView>(
        `/v1/corporate/organizations/${workspace.context.organization.organization_id}/delegation`,
        { sessionToken: session },
      ).catch(() => null)
    : null;
  return {
    status: "ok",
    workspace,
    invitations,
    grantableRoles:
      delegation?.authorization_revision === workspace.context.organization.authorization_revision
        ? delegation.grantable_roles.map((role) => role.name)
        : null,
  } as const;
}

function PeopleStats({
  items,
}: {
  items: readonly { label: string; count: number | null; icon: IconName }[];
}) {
  return (
    <dl className="grid grid-cols-2 gap-3 xl:grid-cols-4" data-ui="people-stats">
      {items.map((item) => (
        <div
          key={item.label}
          className="border-border bg-card flex min-w-0 items-center gap-4 rounded-lg border px-5 py-4"
        >
          <Icon name={item.icon} size="lg" className="shrink-0" />
          <div>
            <dd className="text-2xl leading-tight font-medium tabular-nums">{item.count ?? "—"}</dd>
            <dt className="text-muted-foreground mt-1 text-sm">{item.label}</dt>
          </div>
        </div>
      ))}
    </dl>
  );
}

export default async function CorporateAdministrationPage({
  params,
  searchParams,
  accessView = false,
}: PageProps & { accessView?: boolean }) {
  const { locale } = await params;
  const filters = await searchParams;
  const tab = !accessView && filters.tab === "invitations" ? "invitations" : "members";
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins`);
  const t = await getTranslations("people");
  const h = await getTranslations("hub");
  const common = await getTranslations("common");
  let data: Awaited<ReturnType<typeof loadAdminData>>;
  try {
    data = await loadAdminData();
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE")
      return (
        <StatePanel kind="error" title={common("error")} description={common("apiUnavailable")} />
      );
    throw error;
  }
  if (data.status !== "ok")
    return (
      <StatePanel
        kind={data.status === "empty" ? "empty" : "error"}
        title={h("membersAndInvitations")}
        description={data.status === "empty" ? t("noOrganization") : t("forbidden")}
      />
    );
  const csrfToken = (await readCsrfToken()) ?? "";
  return (
    <AdministrationContent data={data} accessView={accessView} tab={tab} csrfToken={csrfToken} />
  );
}
async function AdministrationContent({
  data,
  accessView,
  tab,
  csrfToken,
}: {
  data: Extract<Awaited<ReturnType<typeof loadAdminData>>, { status: "ok" }>;
  accessView: boolean;
  tab: string;
  csrfToken: string;
}) {
  const t = await getTranslations("people");
  const h = await getTranslations("hub");
  const { workspace, invitations } = data;

  const { context, members, roles, jobTitles } = workspace;
  const now = new Date().toISOString();
  const title = h(accessView ? "employeeAccess" : "membersAndInvitations");
  const canViewInvitations = context.capabilities.includes("member.invite");
  return (
    <div className="min-w-0 space-y-5" data-ui="members-invitations-page">
      <header className="space-y-3">
        <nav
          aria-label={t("breadcrumbs")}
          className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs sm:text-sm"
        >
          <Link href="/corporate/overview" className="hover:text-foreground">
            {t("corporate")}
          </Link>
          <span aria-hidden>/</span>
          <span>{t("administration")}</span>
          <span aria-hidden>/</span>
          <span>{t("peopleAndAccess")}</span>
          <span aria-hidden>/</span>
          <span aria-current="page" className="text-foreground">
            {title}
          </span>
        </nav>
        <div className="space-y-1">
          <h1 className="text-3xl leading-tight font-medium tracking-tight">{title}</h1>
          <p className="text-muted-foreground text-sm sm:text-base">{t("pageBody")}</p>
        </div>
      </header>
      {!accessView ? (
        <>
          <PeopleStats
            items={[
              { label: t("totalMembers"), count: members?.items.length ?? null, icon: "team" },
              {
                label: t("pendingInvitations"),
                count:
                  invitations?.items.filter((invitation) =>
                    isOutstandingInvitation(invitation, Date.parse(now)),
                  ).length ?? null,
                icon: "mail",
              },
              { label: t("teams"), count: context.teams.length, icon: "team" },
              { label: t("roles"), count: roles?.items.length ?? null, icon: "access" },
            ]}
          />
          <NavigationTabs
            variant="underline"
            ariaLabel={title}
            items={[
              {
                key: "members",
                href: "/corporate/organization/admins?tab=members",
                label: t("members"),
                active: tab === "members",
              },
              ...(canViewInvitations
                ? [
                    {
                      key: "invitations",
                      href: "/corporate/organization/admins?tab=invitations",
                      label: t("invitations"),
                      active: tab === "invitations",
                    },
                  ]
                : []),
            ]}
          />
        </>
      ) : null}
      {tab === "invitations" && canViewInvitations ? (
        <CorporateInvitationsPanel
          csrfToken={csrfToken}
          context={context}
          roles={roles?.items ?? []}
          members={members?.items ?? []}
          invitations={invitations?.items ?? []}
          grantableRoles={data.grantableRoles}
          now={now}
          unavailable={invitations === null}
        />
      ) : (
        <CorporateMembersDirectory
          members={members?.items ?? []}
          context={context}
          roles={roles?.items ?? []}
          jobTitles={jobTitles?.items ?? []}
          csrfToken={csrfToken}
          now={now}
        />
      )}
    </div>
  );
}
