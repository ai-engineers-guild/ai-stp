"use client";

import { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import type { HeartbeatReport as HeartbeatReportData } from "@/lib/api/generated/types.gen";
import { Link, usePathname, useRouter } from "@/lib/i18n/navigation";

type Status = HeartbeatReportData["items"][number]["status"];
export type { HeartbeatReportData };

const STATUSES: Status[] = ["active", "stale", "failing", "disabled", "unknown"];
const BADGES = {
  active: "success",
  stale: "warning",
  failing: "destructive",
  disabled: "secondary",
  unknown: "outline",
} as const;
const BUCKET_COLORS = {
  healthy: "bg-success",
  partial: "bg-warning",
  missing: "bg-destructive",
  not_expected: "bg-muted",
} as const;

function relativeTime(value: string | null, now: string, locale: string, never: string): string {
  if (!value) return never;
  const seconds = Math.max(0, Math.floor((Date.parse(now) - Date.parse(value)) / 1000));
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (seconds < 60) return formatter.format(-seconds, "second");
  if (seconds < 3600) return formatter.format(-Math.floor(seconds / 60), "minute");
  if (seconds < 86400) return formatter.format(-Math.floor(seconds / 3600), "hour");
  return formatter.format(-Math.floor(seconds / 86400), "day");
}

// Filters and both views share one URL state and one table shell.
// eslint-disable-next-line max-lines-per-function
export function CorporateHeartbeatReport({
  report,
  view,
  period,
  fromDate,
  toDate,
  selectedTeams,
  selectedEmployees,
  selectedStatuses,
  sort,
  order,
  locale,
}: {
  report: HeartbeatReportData;
  view: "current" | "history";
  period: "24h" | "7d" | "30d" | "custom";
  fromDate: string;
  toDate: string;
  selectedTeams: string[];
  selectedEmployees: string[];
  selectedStatuses: Status[];
  sort: string;
  order: "asc" | "desc";
  locale: string;
}) {
  const t = useTranslations("corporateReports");
  const router = useRouter();
  const path = usePathname();
  const query = (changes: Record<string, string | string[] | null>) => {
    const params = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries(changes)) {
      params.delete(key);
      if (Array.isArray(value))
        value.forEach((item) => {
          params.append(key, item);
        });
      else if (value) params.set(key, value);
    }
    return `${path}?${params.toString()}`;
  };
  const change = (changes: Record<string, string | string[] | null>) => {
    router.push(query({ ...changes, page: null }));
  };
  const employees = report.employees.filter(
    (employee) =>
      selectedTeams.length === 0 || employee.team_ids.some((id) => selectedTeams.includes(id)),
  );
  const first = (report.page - 1) * report.page_size + 1;
  const last = Math.min(report.page * report.page_size, report.total);
  const sortable = (key: string, label: string) => (
    <button
      type="button"
      aria-label={label}
      className="focus-visible:ring-ring inline-flex items-center gap-1 text-left hover:underline focus-visible:ring-2"
      onClick={() => {
        change({ sort: key, order: sort === key && order === "asc" ? "desc" : "asc" });
      }}
    >
      {label} <span aria-hidden="true">{sort === key ? (order === "asc" ? "↑" : "↓") : "↕"}</span>
    </button>
  );
  return (
    <>
      <div className="border-border bg-card grid gap-4 rounded-lg border p-4 md:grid-cols-[repeat(3,minmax(0,1fr))_auto] xl:items-end">
        <SearchableMultiSelect
          name="team"
          label={selectedTeams.length ? t("team") : t("allTeams")}
          searchLabel={t("searchTeams")}
          options={report.teams.map((team) => ({ value: team.id, label: team.name }))}
          selected={selectedTeams}
          onChange={(value) => {
            const validEmployees = report.employees.filter(
              (employee) =>
                value.length === 0 || employee.team_ids.some((id) => value.includes(id)),
            );
            change({
              team: value,
              employee: selectedEmployees.filter((id) => validEmployees.some((e) => e.id === id)),
            });
          }}
          closeLabel={t("close")}
        />
        <SearchableMultiSelect
          name="employee"
          label={selectedEmployees.length ? t("employee") : t("allEmployees")}
          searchLabel={t("searchEmployees")}
          options={employees.map((employee) => ({ value: employee.id, label: employee.name }))}
          selected={selectedEmployees}
          onChange={(value) => {
            change({ employee: value });
          }}
          closeLabel={t("close")}
        />
        <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-1 xl:grid-cols-2">
          {view === "history" && (
            <label className="text-muted-foreground text-xs">
              {t("period")}
              <select
                className="border-border bg-background text-foreground mt-1 block h-11 w-full rounded-sm border px-2 text-sm"
                value={period}
                onChange={(event) => {
                  if (event.target.value === "custom") {
                    const today = report.evaluated_at.slice(0, 10);
                    const weekAgo = new Date(Date.parse(report.evaluated_at) - 6 * 86400_000)
                      .toISOString()
                      .slice(0, 10);
                    change({ period: "custom", from_date: weekAgo, to_date: today });
                  } else change({ period: event.target.value, from_date: null, to_date: null });
                }}
              >
                <option value="24h">{t("period24h")}</option>
                <option value="7d">{t("period7d")}</option>
                <option value="30d">{t("period30d")}</option>
                <option value="custom">{t("periodCustom")}</option>
              </select>
            </label>
          )}
          {view === "history" && period === "custom" && (
            <div className="flex gap-2">
              <label className="text-muted-foreground text-xs">
                {t("fromDate")}
                <input
                  type="date"
                  value={fromDate}
                  max={toDate}
                  onChange={(event) => {
                    change({ from_date: event.target.value });
                  }}
                  className="border-border bg-background text-foreground mt-1 block h-11 w-full rounded-sm border px-2 text-sm"
                />
              </label>
              <label className="text-muted-foreground text-xs">
                {t("toDate")}
                <input
                  type="date"
                  value={toDate}
                  min={fromDate}
                  onChange={(event) => {
                    change({ to_date: event.target.value });
                  }}
                  className="border-border bg-background text-foreground mt-1 block h-11 w-full rounded-sm border px-2 text-sm"
                />
              </label>
            </div>
          )}
          <SearchableMultiSelect
            name="status"
            label={selectedStatuses.length ? t("status") : t("allStatuses")}
            searchLabel={t("searchStatuses")}
            options={STATUSES.map((status) => ({ value: status, label: t(status) }))}
            selected={selectedStatuses}
            onChange={(value) => {
              change({ status: value });
            }}
            closeLabel={t("close")}
          />
        </div>
        <div
          role="group"
          aria-label={t("heartbeat")}
          className="border-border flex rounded-sm border"
        >
          {(["current", "history"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={view === option}
              className={`focus-visible:ring-ring min-h-11 px-4 text-sm focus-visible:ring-2 ${view === option ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
              onClick={() => {
                change({ view: option });
              }}
            >
              {t(option)}
            </button>
          ))}
        </div>
      </div>
      {view === "history" && (
        <p className="text-muted-foreground mt-3 text-xs">
          {t("policy", {
            interval: `${Math.round(report.interval_seconds / 60)} min`,
            stale: `${Math.round(report.stale_after_seconds / 60)} min`,
          })}
        </p>
      )}
      <div className="mt-8 flex flex-wrap items-center justify-between gap-3 text-sm">
        <span className="text-muted-foreground">{t("devices", { count: report.total })}</span>
        <div className="flex items-center gap-3">
          <label className="text-muted-foreground flex items-center gap-2">
            {t("perPage")}
            <select
              value={report.page_size}
              onChange={(event) => {
                change({ page_size: event.target.value });
              }}
              className="border-border bg-background text-foreground h-9 rounded-sm border px-2"
            >
              {[10, 25, 50].map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
          <span>
            {t("pageRange", { from: report.total ? first : 0, to: last, total: report.total })}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={report.page <= 1}
            aria-label={t("previous")}
            onClick={() => {
              router.push(query({ page: String(report.page - 1) }));
            }}
          >
            ‹
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={last >= report.total}
            aria-label={t("next")}
            onClick={() => {
              router.push(query({ page: String(report.page + 1) }));
            }}
          >
            ›
          </Button>
        </div>
      </div>
      <div className="border-border mt-4 overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead className="bg-card text-muted-foreground border-border border-b">
            <tr>
              <th className="px-4 py-3 font-medium">{sortable("employee", t("employee"))}</th>
              <th className="px-4 py-3 font-medium">{sortable("team", t("team"))}</th>
              <th className="px-4 py-3 font-medium">{t("device")}</th>
              {view === "history" && (
                <th className="px-4 py-3 font-medium">{t("heartbeatHistory")}</th>
              )}
              <th className="px-4 py-3 font-medium">
                {sortable("last_heartbeat", t("lastHeartbeat"))}
              </th>
              <th className="px-4 py-3 font-medium">
                {sortable(
                  view === "history" ? "coverage" : "status",
                  view === "history" ? t("coveragePercent") : t("status"),
                )}
              </th>
            </tr>
          </thead>
          <tbody>
            {report.items.map((row) => (
              <tr key={row.device_id} className="border-border border-b last:border-0">
                <td className="px-4 py-3">
                  <Link
                    href={`/corporate/employees/${row.account_id}`}
                    className="hover:text-primary underline"
                  >
                    {row.employee_name}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  {row.teams.map((team, index) => (
                    <span key={team.id}>
                      {index > 0 && ", "}
                      <Link
                        href={`/corporate/teams/${team.id}`}
                        className="hover:text-primary underline"
                      >
                        {team.name}
                      </Link>
                    </span>
                  ))}
                </td>
                <td className="px-4 py-3">{row.device_name}</td>
                {view === "history" && (
                  <td className="px-4 py-3">
                    <div
                      className="flex min-w-52 gap-px"
                      role="group"
                      aria-label={t("heartbeatHistory")}
                    >
                      {(row.buckets ?? []).map((bucket, index) => (
                        <button
                          key={index}
                          type="button"
                          className={`focus-visible:ring-ring h-3 min-w-0 flex-1 focus-visible:ring-2 ${BUCKET_COLORS[bucket.state]}`}
                          title={`${new Date(bucket.start).toLocaleString(locale)}–${new Date(bucket.end).toLocaleString(locale)} · ${t("expected")}: ${bucket.expected} · ${t("received")}: ${bucket.received} · ${t("coveragePercent")}: ${bucket.expected ? Math.round((100 * Math.min(bucket.received, bucket.expected)) / bucket.expected) : 0}%`}
                          aria-label={`${t("expected")}: ${bucket.expected}, ${t("received")}: ${bucket.received}`}
                        />
                      ))}
                    </div>
                    <div
                      aria-hidden="true"
                      className="text-muted-foreground mt-1 flex justify-between text-[10px]"
                    >
                      {[0, 15, 30, 45, 59].map((index) => (
                        <span key={index}>
                          {row.buckets?.[index]
                            ? new Intl.DateTimeFormat(
                                locale,
                                period === "24h"
                                  ? { hour: "2-digit" }
                                  : { day: "numeric", month: "short" },
                              ).format(new Date(row.buckets[index].start))
                            : ""}
                        </span>
                      ))}
                    </div>
                  </td>
                )}
                <td
                  className="px-4 py-3"
                  title={
                    row.last_heartbeat_at
                      ? new Date(row.last_heartbeat_at).toLocaleString(locale)
                      : undefined
                  }
                >
                  {relativeTime(row.last_heartbeat_at, report.evaluated_at, locale, t("never"))}
                </td>
                <td className="px-4 py-3">
                  {view === "history" ? (
                    row.coverage_percent === null || row.coverage_percent === undefined ? (
                      "—"
                    ) : (
                      <span className="flex items-center gap-2">
                        {row.coverage_percent}%
                        <span className="bg-muted h-1.5 w-20 rounded-sm">
                          <span
                            className={`block h-full rounded-sm ${row.coverage_percent >= 90 ? "bg-success" : row.coverage_percent >= 60 ? "bg-warning" : "bg-destructive"}`}
                            style={{ width: `${row.coverage_percent}%` }}
                          />
                        </span>
                      </span>
                    )
                  ) : (
                    <Badge variant={BADGES[row.status]}>● {t(row.status)}</Badge>
                  )}
                </td>
              </tr>
            ))}
            {report.items.length === 0 && (
              <tr>
                <td colSpan={view === "history" ? 6 : 5} className="px-4 py-12 text-center">
                  <p>{t("empty")}</p>
                  <p className="text-muted-foreground mt-2">{t("emptyHint")}</p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
