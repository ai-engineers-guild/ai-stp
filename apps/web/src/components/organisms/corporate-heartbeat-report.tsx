"use client";

import { Select } from "@/components/atoms/select";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import {
  groupByEmployee,
  HeartbeatEmployeeRows,
} from "@/components/molecules/corporate-heartbeat-rows";
import type { HeartbeatReport as HeartbeatReportData } from "@/lib/api/generated/types.gen";
import { usePathname, useRouter } from "@/lib/i18n/navigation";

type Status = HeartbeatReportData["items"][number]["status"];
export type { HeartbeatReportData };

const STATUSES: Status[] = ["active", "stale", "failing", "disabled", "unknown"];

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
  const selectionKey = JSON.stringify([selectedTeams, selectedEmployees, selectedStatuses]);
  const [syncedKey, setSyncedKey] = useState(selectionKey);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const toggleExpanded = (accountId: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(accountId)) next.delete(accountId);
      else next.add(accountId);
      return next;
    });
  };
  const [selection, setSelection] = useState(() => ({
    teams: selectedTeams,
    employees: selectedEmployees,
    statuses: selectedStatuses,
  }));
  if (syncedKey !== selectionKey) {
    setSyncedKey(selectionKey);
    setSelection({
      teams: selectedTeams,
      employees: selectedEmployees,
      statuses: selectedStatuses,
    });
  }
  const pendingQuery = useRef<URLSearchParams | null>(null);
  const filterTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (filterTimer.current) clearTimeout(filterTimer.current);
    },
    [],
  );
  const query = (changes: Record<string, string | string[] | null>) => {
    const params = new URLSearchParams(pendingQuery.current ?? window.location.search);
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
    if (filterTimer.current) clearTimeout(filterTimer.current);
    const next = query({ ...changes, page: null });
    pendingQuery.current = null;
    router.push(next);
  };
  const changeFilter = (changes: Record<string, string | string[] | null>) => {
    const next = query({ ...changes, page: null });
    pendingQuery.current = new URLSearchParams(next.split("?")[1]);
    if (filterTimer.current) clearTimeout(filterTimer.current);
    filterTimer.current = setTimeout(() => {
      pendingQuery.current = null;
      router.replace(next, { scroll: false });
    }, 250);
  };
  const employees = report.employees.filter(
    (employee) =>
      selection.teams.length === 0 || employee.team_ids.some((id) => selection.teams.includes(id)),
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
      <div className="border-border bg-card grid items-end gap-4 rounded-lg border p-4 md:grid-cols-[repeat(3,minmax(0,1fr))_auto]">
        <SearchableMultiSelect
          name="team"
          label={selection.teams.length ? t("team") : t("allTeams")}
          searchLabel={t("searchTeams")}
          options={report.teams.map((team) => ({ value: team.id, label: team.name }))}
          selected={selection.teams}
          onChange={(value) => {
            const validEmployees = report.employees.filter(
              (employee) =>
                value.length === 0 || employee.team_ids.some((id) => value.includes(id)),
            );
            const nextEmployees = selection.employees.filter((id) =>
              validEmployees.some((employee) => employee.id === id),
            );
            setSelection({ ...selection, teams: value, employees: nextEmployees });
            changeFilter({
              team: value,
              employee: nextEmployees,
            });
          }}
          closeLabel={t("close")}
        />
        <SearchableMultiSelect
          name="employee"
          label={selection.employees.length ? t("employee") : t("allEmployees")}
          searchLabel={t("searchEmployees")}
          options={employees.map((employee) => ({ value: employee.id, label: employee.name }))}
          selected={selection.employees}
          onChange={(value) => {
            setSelection({ ...selection, employees: value });
            changeFilter({ employee: value });
          }}
          closeLabel={t("close")}
        />
        <div className="grid items-end gap-2 sm:grid-cols-2 md:grid-cols-1 xl:grid-cols-2">
          {view === "history" && (
            <label className="text-muted-foreground text-xs">
              {t("period")}
              <Select
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
              </Select>
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
            label={selection.statuses.length ? t("status") : t("allStatuses")}
            searchLabel={t("searchStatuses")}
            options={STATUSES.map((status) => ({ value: status, label: t(status) }))}
            selected={selection.statuses}
            onChange={(value) => {
              setSelection({ ...selection, statuses: value as Status[] });
              changeFilter({ status: value });
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
            <Select
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
            </Select>
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
        <Table className="min-w-[900px] text-left">
          <THead className="bg-card text-muted-foreground border-border border-b">
            <Tr className="border-b-0">
              <Th className="px-4 py-3">{sortable("employee", t("employee"))}</Th>
              <Th className="px-4 py-3">{sortable("team", t("team"))}</Th>
              <Th className="px-4 py-3">{t("device")}</Th>
              {view === "history" && <Th className="px-4 py-3">{t("heartbeatHistory")}</Th>}
              <Th className="px-4 py-3">{sortable("last_heartbeat", t("lastHeartbeat"))}</Th>
              <Th className="px-4 py-3">
                {sortable(
                  view === "history" ? "coverage" : "status",
                  view === "history" ? t("coveragePercent") : t("status"),
                )}
              </Th>
            </Tr>
          </THead>
          <TBody>
            {groupByEmployee(report.items).map(({ accountId, rows }) => (
              <HeartbeatEmployeeRows
                key={accountId}
                rows={rows}
                view={view}
                period={period}
                evaluatedAt={report.evaluated_at}
                locale={locale}
                expanded={expanded.has(accountId)}
                onToggle={() => {
                  toggleExpanded(accountId);
                }}
                t={t}
              />
            ))}
            {report.items.length === 0 && (
              <Tr>
                <Td colSpan={view === "history" ? 6 : 5} className="px-4 py-12 text-center">
                  <p>{t("empty")}</p>
                  <p className="text-muted-foreground mt-2">{t("emptyHint")}</p>
                </Td>
              </Tr>
            )}
          </TBody>
        </Table>
      </div>
    </>
  );
}
