import { getTranslations, setRequestLocale } from "next-intl/server";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { LocalizedResourceActions } from "@/components/organisms/localized-corporate-resource-actions";
import { StatePanel } from "@/components/molecules/state-panel";
import { readCorporateMemberAccess } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";

export default async function EmployeeAccessPage({
  params,
}: {
  params: Promise<{ locale: string; accountId: string }>;
}) {
  const { locale, accountId } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/employees/${accountId}`);
  const t = await getTranslations("corporate");
  const technology = await getTranslations("technology");
  const result = await readCorporateMemberAccess((await sessionCookieValue()) ?? "", accountId);
  if (!result)
    return (
      <StatePanel
        kind="error"
        title={t("accessAdministration")}
        description={technology("forbidden")}
      />
    );
  const member = result.member;
  return (
    <div className="space-y-6">
      <HistoryBackButton label={t("backToWorkspace")} fallback="/corporate/organization/admins" />
      <h1 className="text-3xl font-medium tracking-tight">{t("accessAdministration")}</h1>
      <Link href={`/corporate/employees/${accountId}`} className="underline underline-offset-4">
        {member.display_name ?? t("member")}
      </Link>
      <LocalizedResourceActions
        resource="members"
        resourceId={accountId}
        name={member.display_name ?? t("member")}
        role={member.role}
        state={member.state}
        revision={member.revision}
        organizationId={result.organization.organization_id}
        authorizationRevision={result.organization.authorization_revision}
        csrfToken={(await readCsrfToken()) ?? ""}
        roles={result.roles?.items ?? []}
        permissions={result.context.capabilities}
        availableActions={result.context.capabilities}
      />
    </div>
  );
}
