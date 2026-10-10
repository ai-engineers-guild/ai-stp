import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateAuditPanel } from "@/components/organisms/corporate-audit-panel";
import { corporateAuditFilterValues, readCorporateAudit } from "@/lib/api/corporate-audit";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { PeopleHeader } from "@/app/[locale]/(site)/corporate/admins/people-shared";

export default async function CorporateAuditPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/admins/audit`);
  const t = await getTranslations("corporate");
  const hub = await getTranslations("hub");
  const common = await getTranslations("common");
  const technology = await getTranslations("technology");
  const rawSearchParams = await searchParams;
  let result;
  try {
    result = await readCorporateAudit((await sessionCookieValue()) ?? "", rawSearchParams);
  } catch {
    return (
      <StatePanel kind="error" title={t("auditJournal")} description={common("apiUnavailable")} />
    );
  }
  if (!result)
    return (
      <StatePanel kind="error" title={t("auditJournal")} description={technology("forbidden")} />
    );
  return (
    <div className="min-w-0 space-y-6">
      <PeopleHeader
        section={hub("audit")}
        current={t("auditJournal")}
        description={t("auditJournalDescription")}
      />
      <CorporateAuditPanel
        organizationId={result.context.organization.organization_id}
        audit={result.audit}
        canExport={result.context.capabilities.includes("audit.export")}
        members={result.members?.items ?? []}
        filters={corporateAuditFilterValues(rawSearchParams)}
        page={result.page}
        pageSize={result.size}
        labels={{
          title: t("auditJournal"),
          export: t("exportAudit"),
          exporting: t("exportingAudit"),
          exportFormat: t("exportFormat"),
          exportRange: t("exportRange"),
          currentFilters: t("currentFilters"),
          today: t("today"),
          last7Days: t("last7Days"),
          last30Days: t("last30Days"),
          allEvents: t("allEvents"),
          json: t("json"),
          csv: t("csv"),
          noAudit: t("noAudit"),
          failed: common("apiUnavailable"),
        }}
      />
    </div>
  );
}
