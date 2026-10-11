import { getTranslations } from "next-intl/server";
import { Link } from "@/lib/i18n/navigation";
import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";
import { NavigationTabs } from "@/components/molecules/navigation-tabs";
import type { RuntimeUsageReport } from "@/lib/api/generated/types.gen";

const WEEKDAYS = [
  { key: "weekdayMon", fullKey: "fullWeekdayMon" },
  { key: "weekdayTue", fullKey: "fullWeekdayTue" },
  { key: "weekdayWed", fullKey: "fullWeekdayWed" },
  { key: "weekdayThu", fullKey: "fullWeekdayThu" },
  { key: "weekdayFri", fullKey: "fullWeekdayFri" },
  { key: "weekdaySat", fullKey: "fullWeekdaySat" },
  { key: "weekdaySun", fullKey: "fullWeekdaySun" },
] as const;

export async function UsageReportCharts({
  data,
  chart,
  dayQuery,
  hourQuery,
  detailHref,
}: {
  data: RuntimeUsageReport;
  chart: "day" | "hour";
  dayQuery: URLSearchParams;
  hourQuery: URLSearchParams;
  detailHref: (changes: Record<string, string>) => string;
}) {
  const t = await getTranslations("corporateReports");
  const maxDayUses = Math.max(1, ...data.by_day.map((bucket) => bucket.uses));
  const hourlyUses = new Map(
    data.by_hour.map((bucket) => [`${bucket.weekday}:${bucket.hour}`, bucket.uses]),
  );
  const maxHourUses = Math.max(1, ...hourlyUses.values());

  return (
    <section
      aria-label={t("usageChart")}
      className="border-border bg-card mb-5 rounded-lg border p-4"
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-medium">{t("usageOverTime")}</h2>
        <NavigationTabs
          ariaLabel={t("chartMode")}
          variant="segmented"
          items={[
            {
              key: "day",
              label: t("byDay"),
              active: chart === "day",
              href: `/corporate/reports/usage?${dayQuery}`,
            },
            {
              key: "hour",
              label: t("byHour"),
              active: chart === "hour",
              href: `/corporate/reports/usage?${hourQuery}`,
            },
          ]}
        />
      </div>
      {chart === "day" ? (
        data.by_day.length ? (
          <div
            className="flex h-32 items-end gap-1 overflow-x-auto"
            aria-label={t("recordedUsesByDay")}
          >
            {data.by_day.map((bucket) => (
              <Link
                key={bucket.day}
                href={detailHref({ detail_day: bucket.day, detail_page: "" })}
                className="flex h-full min-w-9 flex-1 flex-col items-center justify-end"
                title={t("bucketDayTitle", { day: bucket.day, uses: bucket.uses })}
                aria-label={t("bucketDayAria", { day: bucket.day, uses: bucket.uses })}
              >
                <span
                  className="bg-primary block w-full rounded-t-sm"
                  style={{ height: `${Math.max(3, (bucket.uses / maxDayUses) * 100)}%` }}
                />
                <span className="text-muted-foreground mt-1 text-xs">{bucket.day.slice(5)}</span>
              </Link>
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">{t("noRecordedUses")}</p>
        )
      ) : (
        <div className="overflow-x-auto">
          <Table className="min-w-175 text-xs" aria-label={t("recordedUsesByWeekdayHour")}>
            <THead>
              <Tr className="border-b-0">
                <Th className="h-auto px-0 font-normal">{t("hour")}</Th>
                {WEEKDAYS.map((day) => (
                  <Th key={day.key} className="h-auto px-1 font-normal">
                    {t(day.key)}
                  </Th>
                ))}
              </Tr>
            </THead>
            <TBody>
              {Array.from({ length: 24 }, (_, hour) => (
                <Tr key={hour} className="border-b-0">
                  <Th scope="row" className="h-auto pr-2 pl-0 text-left font-normal">
                    {hour.toString().padStart(2, "0")}
                  </Th>
                  {[0, 1, 2, 3, 4, 5, 6].map((weekday) => {
                    const uses = hourlyUses.get(`${weekday}:${hour}`) ?? 0;
                    const dayInfo = WEEKDAYS[weekday] ?? WEEKDAYS[0];
                    return (
                      <Td key={weekday} className="p-0.5">
                        <Link
                          href={detailHref({
                            detail_weekday: String(weekday),
                            detail_hour: String(hour),
                            detail_page: "",
                          })}
                          aria-label={t("heatmapAria", {
                            weekday: t(dayInfo.fullKey),
                            hour,
                            uses,
                          })}
                          title={t("heatmapTitle", { uses })}
                          className="bg-primary block h-4 rounded-sm"
                          style={{
                            opacity: uses ? Math.max(0.2, uses / maxHourUses) : 0.06,
                          }}
                        />
                      </Td>
                    );
                  })}
                </Tr>
              ))}
            </TBody>
          </Table>
        </div>
      )}
      <p className="text-muted-foreground mt-2 text-xs">
        {t("timezone", { timezone: data.report_timezone })}
      </p>
    </section>
  );
}
