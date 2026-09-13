import { getTranslations, setRequestLocale } from "next-intl/server";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateAuditPanel } from "@/components/organisms/corporate-audit-panel";
import { readCorporateAudit, corporateAuditFilters } from "@/lib/api/corporate";
import { Button } from "@/components/atoms/button";
import { Label } from "@/components/atoms/label";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";

export default async function CorporateAuditPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/audit`);
  const t = await getTranslations("corporate");
  const auditLabels = await getTranslations("corporate.auditUi");
  const common = await getTranslations("common");
  const technology = await getTranslations("technology");
  const filters = corporateAuditFilters(await searchParams);
  let result;
  try {
    result = await readCorporateAudit((await sessionCookieValue()) ?? "", await searchParams);
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
    <div className="space-y-6">
      <HistoryBackButton label={t("backToWorkspace")} fallback="/corporate/organization/admins" />
      <h1 className="text-3xl font-medium tracking-tight">{t("auditJournal")}</h1>
      {result.members && (
        <form className="flex flex-wrap items-end gap-3">
          <div className="min-w-56 space-y-2">
            <Label htmlFor="audit-employee">{t("member")}</Label>
            <select
              id="audit-employee"
              name="actor_account_id"
              defaultValue={filters.actor_account_id ?? ""}
              className="border-input bg-background min-h-11 w-full rounded-sm border px-3 text-sm"
            >
              <option value="">{auditLabels("allEmployees")}</option>
              {result.members.items
                .filter((member) => member.display_name)
                .map((member) => (
                  <option key={member.account_id} value={member.account_id}>
                    {member.display_name}
                  </option>
                ))}
            </select>
          </div>
          <Button type="submit">{auditLabels("filterEvents")}</Button>
        </form>
      )}
      <CorporateAuditPanel
        organizationId={result.context.organization.organization_id}
        audit={result.audit}
        members={result.members?.items ?? []}
        labels={{
          title: t("auditJournal"),
          export: t("exportAudit"),
          exporting: t("exportingAudit"),
          noAudit: t("noAudit"),
          failed: common("apiUnavailable"),
        }}
      />
      <nav aria-label={t("auditJournal")} className="flex flex-wrap gap-4">
        <Link
          href={`/corporate/organization/admins/audit?${new URLSearchParams(filters)}`}
          className="inline-flex min-h-11 items-center underline underline-offset-4"
        >
          {auditLabels("latestEvents")}
        </Link>
        {result.audit.next_before_id && result.audit.next_before_created_at && (
          <Link
            href={`/corporate/organization/admins/audit?${new URLSearchParams({ ...filters, before_id: String(result.audit.next_before_id), before_created_at: result.audit.next_before_created_at })}`}
            className="inline-flex min-h-11 items-center underline underline-offset-4"
          >
            {auditLabels("olderEvents")}
          </Link>
        )}
      </nav>
    </div>
  );
}
