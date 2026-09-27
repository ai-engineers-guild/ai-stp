import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { Link } from "@/lib/i18n/navigation";
import { readCorporateContext } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { StatePanel } from "@/components/molecules/state-panel";
import { NavigationTabs } from "@/components/molecules/navigation-tabs";
import type { CorporateContext, RuntimeUsageReport } from "@/lib/api/generated/types.gen";
import {
  parseUsageQuery,
  fetchUsageReportData,
  fetchUsageEventsData,
  sortObjects,
  sortEmployees,
  buildDisplayRows,
  buildEmployeeOptions,
  buildUsageHrefs,
  type UsageQueryParams,
} from "./usage-report-data";
import { UsageReportFilters } from "./usage-report-filters";
import { UsageReportCharts } from "./usage-report-charts";
import { UsageReportTable } from "./usage-report-table";
import { UsageReportDrawer } from "./usage-report-drawer";

type Translator = Awaited<ReturnType<typeof getTranslations<"corporateReports">>>;

function UsageStatusNotice({ data, t }: { data: RuntimeUsageReport; t: Translator }) {
  return (
    <div
      role="status"
      className="border-border bg-muted/30 mb-4 rounded-lg border px-4 py-3 text-sm"
    >
      {!data.usage_collection_enabled && <p>{t("usageCollectionOff")}</p>}
      {data.usage_collection_enabled && <p>{t("nativeCoveragePartial")}</p>}
      {!data.inventory_scan_enabled ? (
        <p>{t("inventoryScanningOff")}</p>
      ) : (
        data.inventory_employees.some((row) => row.coverage !== "complete") && (
          <p>{t("inventoryChecksPartial")}</p>
        )
      )}
    </div>
  );
}

async function UsageReportBody({
  data,
  parsed,
  context,
  token,
  t,
}: {
  data: RuntimeUsageReport;
  parsed: ReturnType<typeof parseUsageQuery>;
  context: CorporateContext;
  token: string;
  t: Translator;
}) {
  const teamNames = new Map(context.teams.map((team) => [team.team_id, team.name]));
  const inventoryByEmployee = new Map(
    data.inventory_employees.map((row) => [row.employee_id, row]),
  );

  const chartQuery = new URLSearchParams(parsed.viewQuery);
  if (parsed.view === "objects") chartQuery.set("view", "objects");
  const dayQuery = new URLSearchParams(chartQuery);
  dayQuery.set("chart", "day");
  const hourQuery = new URLSearchParams(chartQuery);
  hourQuery.set("chart", "hour");

  const direction = parsed.order === "asc" ? 1 : -1;
  const setupRows = sortObjects(
    data.objects.filter((row) => row.object_kind === "setup"),
    parsed.sort,
    direction,
  );
  const directRows = sortObjects(
    data.objects.filter((row) => row.object_kind === "component" && !row.parent_setup_stable_id),
    parsed.sort,
    direction,
  );
  const employeeRows = sortEmployees(data.employees, parsed.sort, direction);

  const objectMode = parsed.view === "objects" || Boolean(parsed.employeeId);
  const totalItems = objectMode ? setupRows.length + directRows.length : employeeRows.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / 10));
  const page = Math.min(parsed.requestedPage, totalPages);

  const hrefs = buildUsageHrefs({
    viewQuery: parsed.viewQuery,
    chartQuery,
    view: parsed.view,
    sort: parsed.sort,
    order: parsed.order,
    expanded: parsed.expanded,
    selected: parsed.selected,
  });

  const displayRows = buildDisplayRows(
    [...setupRows, ...directRows],
    data.objects,
    page,
    parsed.employeeId,
    parsed.expanded,
  );

  const detailOpen = parsed.selected("detail") === "events";
  const detailPage = /^\d+$/.test(parsed.selected("detail_page"))
    ? Math.min(1000, Number(parsed.selected("detail_page")))
    : 0;

  const eventsResult =
    detailOpen && parsed.usageState !== "no_recorded"
      ? await fetchUsageEventsData(
          context.organization.organization_id,
          token,
          parsed.paramsForApi.get("invoked_from") ?? "",
          detailPage,
          parsed.selected,
        )
      : { eventList: null, detailError: null };

  const focusedObject = data.objects.find(
    (row) =>
      row.object_kind === parsed.selected("detail_item") &&
      row.stable_id === parsed.selected("detail_id") &&
      row.version === parsed.selected("detail_version") &&
      (row.parent_setup_stable_id ?? "") === parsed.selected("detail_setup_id"),
  );

  return (
    <>
      <NavigationTabs
        ariaLabel={t("reportView")}
        variant="segmented"
        className="mb-4 w-fit"
        items={[
          {
            key: "employees",
            label: t("viewEmployees"),
            active: parsed.view === "employees",
            href: `/corporate/reports/usage?${parsed.viewQuery}`,
          },
          {
            key: "objects",
            label: t("viewObjects"),
            active: parsed.view === "objects",
            href: `/corporate/reports/usage?${parsed.viewQuery}&view=objects`,
          },
        ]}
      />
      <p className="text-muted-foreground mb-4 text-sm">
        {t("summaryEmployees", { count: data.employees.length })} ·{" "}
        {t("summaryAssignments", {
          count: data.employees.reduce((sum, row) => sum + row.assigned_components, 0),
        })}{" "}
        ·{" "}
        {t("summaryUsed", {
          count: data.employees.reduce((sum, row) => sum + row.used_components, 0),
        })}
      </p>
      <UsageStatusNotice data={data} t={t} />
      <UsageReportCharts
        data={data}
        chart={parsed.chart}
        dayQuery={dayQuery}
        hourQuery={hourQuery}
        detailHref={hrefs.detailHref}
      />
      <UsageReportTable
        data={data}
        objectMode={objectMode}
        displayRows={displayRows}
        employeeRows={employeeRows}
        employeeId={parsed.employeeId}
        expanded={parsed.expanded}
        page={page}
        totalPages={totalPages}
        totalItems={totalItems}
        sort={parsed.sort}
        order={parsed.order}
        teamNames={teamNames}
        inventoryByEmployee={inventoryByEmployee}
        sortHref={hrefs.sortHref}
        pageHref={hrefs.pageHref}
        employeeHref={hrefs.employeeHref}
        objectDetailHref={hrefs.objectDetailHref}
        expandHref={hrefs.expandHref}
        detailHref={hrefs.detailHref}
      />
      {detailOpen && (
        <UsageReportDrawer
          data={data}
          detailError={eventsResult.detailError}
          eventList={eventsResult.eventList}
          detailPage={detailPage}
          chartQuery={chartQuery}
          employeeId={parsed.employeeId}
          selected={parsed.selected}
          detailPageHref={hrefs.detailPageHref}
          focusedObject={focusedObject}
        />
      )}
    </>
  );
}

export default async function FutureCorporateReport({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; report: string }>;
  searchParams: Promise<UsageQueryParams>;
}) {
  const { locale, report } = await params;
  if (report !== "usage" && report !== "coverage" && report !== "provider") notFound();
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/reports/${report}`);
  const t = await getTranslations("corporateReports");

  if (report !== "usage") {
    return (
      <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
        <Link href="/corporate/reports" className="text-muted-foreground underline">
          {t("title")}
        </Link>
        <h1 className="mt-6 text-3xl font-medium">{t(report)}</h1>
        <p className="text-muted-foreground mt-2">{t("later")}</p>
      </main>
    );
  }

  const token = await sessionCookieValue();
  const context = token ? await readCorporateContext(token) : null;
  if (!token || !context) return <StatePanel kind="empty" title={t("usage")} />;

  const query = await searchParams;
  const parsed = parseUsageQuery(query);
  const data = await fetchUsageReportData(
    context.organization.organization_id,
    token,
    parsed.paramsForApi,
  );
  const employeeOptions = buildEmployeeOptions(context, data);

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
      <Link href="/corporate/reports" className="text-muted-foreground underline">
        {t("title")}
      </Link>
      <h1 className="mt-6 text-3xl font-medium">{t("usage")}</h1>
      <p className="text-muted-foreground mt-2 mb-6 text-sm">{t("usageSubtitle")}</p>
      <UsageReportFilters
        context={context}
        employeeOptions={employeeOptions}
        selected={parsed.selected}
        employeeId={parsed.employeeId}
        period={parsed.period}
        usageState={parsed.usageState}
        view={parsed.view}
        chart={parsed.chart}
        sort={parsed.sort}
        order={parsed.order}
        expanded={parsed.expanded}
      />
      {!data ? (
        <StatePanel kind="error" title={t("error")} />
      ) : (
        <UsageReportBody data={data} parsed={parsed} context={context} token={token} t={t} />
      )}
    </main>
  );
}
