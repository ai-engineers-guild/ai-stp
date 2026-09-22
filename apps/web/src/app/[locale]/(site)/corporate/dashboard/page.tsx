import { getTranslations, setRequestLocale } from "next-intl/server";

import { DashboardBuilder } from "@/components/organisms/dashboard-builder";
import { StatePanel } from "@/components/molecules/state-panel";
import { readCorporateContext } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function CorporateDashboard({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/dashboard`);
  const t = await getTranslations("dashboardBuilder");
  const token = await sessionCookieValue();
  const context = token ? await readCorporateContext(token) : null;
  if (!context) return <StatePanel kind="empty" title={t("noOrganization")} />;
  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8 sm:px-6">
      <div>
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground mt-2 text-sm">{t("description")}</p>
      </div>
      <DashboardBuilder
        csrfToken={(await readCsrfToken()) ?? ""}
        accountId={context.member.account_id}
        organizationId={context.organization.organization_id}
        teams={context.teams
          .filter(
            (team) =>
              context.member.role === "superadmin" ||
              team.lead_account_ids.includes(context.member.account_id),
          )
          .map((team) => ({ id: team.team_id, name: team.name }))}
        canShareOrganization={context.member.role === "superadmin"}
        canReadDiagnostics={context.capabilities.includes("audit.read")}
      />
    </main>
  );
}
