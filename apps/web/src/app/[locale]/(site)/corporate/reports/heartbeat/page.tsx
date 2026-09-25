import { getTranslations, setRequestLocale } from "next-intl/server";
import { Button } from "@/components/atoms/button";
import {
  CorporateHeartbeatReport,
  type HeartbeatReportData,
} from "@/components/organisms/corporate-heartbeat-report";
import { StatePanel } from "@/components/molecules/state-panel";
import { Link } from "@/lib/i18n/navigation";
import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";

type Query = Record<string, string | string[] | undefined>;

function values(query: Query, key: string): string[] {
  const raw = query[key];
  return (Array.isArray(raw) ? raw : raw ? [raw] : []).filter((value) => value.length <= 128);
}

export default async function DeviceHeartbeatReportPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Query>;
}) {
  const { locale } = await params;
  const query = await searchParams;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/reports/heartbeat`);
  const t = await getTranslations("corporateReports");
  const token = await sessionCookieValue();
  const context = token ? await readCorporateContext(token) : null;
  if (!token || !context?.capabilities.includes("telemetry.read"))
    return <StatePanel kind="empty" title={t("title")} />;
  const view = query.view === "history" ? "history" : "current";
  const period =
    query.period === "24h" || query.period === "30d" || query.period === "custom"
      ? query.period
      : "7d";
  const sort = ["employee", "team", "last_heartbeat", "status", "coverage"].includes(
    String(query.sort),
  )
    ? String(query.sort)
    : "last_heartbeat";
  const order = query.order === "asc" ? "asc" : "desc";
  const page = Math.max(1, Number(query.page) || 1);
  const pageSize = [10, 25, 50].includes(Number(query.page_size)) ? Number(query.page_size) : 10;
  const selectedTeams = values(query, "team");
  const selectedEmployees = values(query, "employee");
  const selectedStatuses = values(query, "status").filter((status) =>
    ["active", "stale", "failing", "disabled", "unknown"].includes(status),
  ) as ("active" | "stale" | "failing" | "disabled" | "unknown")[];
  const paramsForApi = new URLSearchParams({
    view,
    period,
    sort,
    order,
    page: String(page),
    page_size: String(pageSize),
  });
  if (period === "custom") {
    if (typeof query.from_date === "string") paramsForApi.set("from_date", query.from_date);
    if (typeof query.to_date === "string") paramsForApi.set("to_date", query.to_date);
  }
  selectedTeams.forEach((value) => {
    paramsForApi.append("team", value);
  });
  selectedEmployees.forEach((value) => {
    paramsForApi.append("employee", value);
  });
  selectedStatuses.forEach((value) => {
    paramsForApi.append("status", value);
  });
  let report: HeartbeatReportData | null = null;
  try {
    report = await apiRequest<HeartbeatReportData>(
      `/v1/corporate/organizations/${context.organization.organization_id}/telemetry/heartbeat-report?${paramsForApi}`,
      { sessionToken: token },
    );
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
  }
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
      <nav aria-label={t("title")} className="text-muted-foreground mb-4 text-sm">
        <Link href="/corporate/reports" className="hover:text-foreground underline">
          {t("title")}
        </Link>
        <span aria-hidden="true" className="mx-2">
          ›
        </span>
        <span className="text-foreground">{t("heartbeat")}</span>
      </nav>
      <h1 className="text-3xl font-medium tracking-tight">{t("heartbeat")}</h1>
      <p className="text-muted-foreground mt-2 mb-6">
        {t(view === "history" ? "historyDescription" : "currentDescription")}
      </p>
      {report ? (
        <CorporateHeartbeatReport
          report={report}
          view={view}
          period={period}
          fromDate={typeof query.from_date === "string" ? query.from_date : ""}
          toDate={typeof query.to_date === "string" ? query.to_date : ""}
          selectedTeams={selectedTeams}
          selectedEmployees={selectedEmployees}
          selectedStatuses={selectedStatuses}
          sort={sort}
          order={order}
          locale={locale}
        />
      ) : (
        <StatePanel
          kind="error"
          title={t("error")}
          action={
            <Button asChild>
              <Link href="/corporate/reports/heartbeat">{t("retry")}</Link>
            </Button>
          }
        />
      )}
    </main>
  );
}
