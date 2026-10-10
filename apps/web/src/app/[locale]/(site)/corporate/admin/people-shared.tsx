import type { ReactNode } from "react";
import { getTranslations } from "next-intl/server";

import { apiRequest } from "@/lib/api/http";
import type { CorporateDelegationView } from "@/lib/api/generated/types.gen";
import { readCorporateContext, readCorporateWorkspace } from "@/lib/api/corporate";
import { listCorporateInvitations } from "@/lib/api/corporate-invitations";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";
import { Icon, type IconName } from "@/theme";

export async function loadAdminData() {
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

export type AdminData = Extract<Awaited<ReturnType<typeof loadAdminData>>, { status: "ok" }>;

export function PeopleStats({
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

/** Shared breadcrumb + title block for the administration pages. */
export async function PeopleHeader({
  section,
  current,
  description,
  children,
}: {
  /** Rail group the page belongs to, e.g. `t("peopleAndAccess")`. */
  section: string;
  current: string;
  description?: string;
  /** Optional marker next to the title, e.g. the viewer's role badge. */
  children?: ReactNode;
}) {
  const t = await getTranslations("people");
  return (
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
        <span>{section}</span>
        <span aria-hidden>/</span>
        <span aria-current="page" className="text-foreground">
          {current}
        </span>
      </nav>
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl leading-tight font-medium tracking-tight">{current}</h1>
          {children}
        </div>
        {description ? (
          <p className="text-muted-foreground text-sm sm:text-base">{description}</p>
        ) : null}
      </div>
    </header>
  );
}
