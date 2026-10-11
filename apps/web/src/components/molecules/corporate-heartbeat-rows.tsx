"use client";

import { Fragment } from "react";
import type { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { Td, Tr } from "@/components/atoms/table";
import type { HeartbeatReport as HeartbeatReportData } from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

export type Row = HeartbeatReportData["items"][number];
export type RowStatus = Row["status"];
type T = ReturnType<typeof useTranslations>;

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

// Worst-first: a person's headline status is the worst among their devices.
const SEVERITY: Record<RowStatus, number> = {
  failing: 0,
  stale: 1,
  unknown: 2,
  disabled: 3,
  active: 4,
};

function relativeTime(value: string | null, now: string, locale: string, never: string): string {
  if (!value) return never;
  const seconds = Math.max(0, Math.floor((Date.parse(now) - Date.parse(value)) / 1000));
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (seconds < 60) return formatter.format(-seconds, "second");
  if (seconds < 3600) return formatter.format(-Math.floor(seconds / 60), "minute");
  if (seconds < 86400) return formatter.format(-Math.floor(seconds / 3600), "hour");
  return formatter.format(-Math.floor(seconds / 86400), "day");
}

function utcDateTime(value: string): string {
  return `${new Date(value).toISOString().replace("T", " ").slice(0, 19)} UTC`;
}

export function groupByEmployee(items: Row[]): { accountId: string; rows: Row[] }[] {
  const groups = new Map<string, Row[]>();
  for (const row of items) {
    groups.set(row.account_id, [...(groups.get(row.account_id) ?? []), row]);
  }
  return [...groups.entries()].map(([accountId, rows]) => ({ accountId, rows }));
}

function deviceCells(
  row: Row,
  view: string,
  period: string,
  t: T,
  evaluatedAt: string,
  locale: string,
) {
  return (
    <>
      <Td className="px-4 py-3">{row.device_name}</Td>
      {view === "history" && (
        <Td className="px-4 py-3">
          <div className="flex min-w-52 gap-px" role="group" aria-label={t("heartbeatHistory")}>
            {(row.buckets ?? []).map((bucket, index) => (
              <button
                key={index}
                type="button"
                className={`focus-visible:ring-ring h-3 min-w-0 flex-1 focus-visible:ring-2 ${BUCKET_COLORS[bucket.state]}`}
                title={`${utcDateTime(bucket.start)}–${utcDateTime(bucket.end)} · ${t("expected")}: ${bucket.expected} · ${t("received")}: ${bucket.received} · ${t("coveragePercent")}: ${bucket.expected ? Math.round((100 * Math.min(bucket.received, bucket.expected)) / bucket.expected) : 0}%`}
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
                  ? period === "24h"
                    ? row.buckets[index].start.slice(11, 16)
                    : row.buckets[index].start.slice(5, 10)
                  : ""}
              </span>
            ))}
          </div>
        </Td>
      )}
      <Td
        className="px-4 py-3"
        title={row.last_heartbeat_at ? utcDateTime(row.last_heartbeat_at) : undefined}
      >
        {relativeTime(row.last_heartbeat_at, evaluatedAt, locale, t("never"))}
      </Td>
      <Td className="px-4 py-3">
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
      </Td>
    </>
  );
}

export function HeartbeatEmployeeRows({
  rows,
  view,
  period,
  evaluatedAt,
  locale,
  expanded,
  onToggle,
  t,
}: {
  rows: Row[];
  view: "current" | "history";
  period: string;
  evaluatedAt: string;
  locale: string;
  expanded: boolean;
  onToggle: () => void;
  t: T;
}) {
  const first = rows[0];
  if (!first) return null;
  const personCells = (row: Row, toggle?: React.ReactNode) => (
    <>
      <Td className="px-4 py-3">
        <span className="flex items-center gap-1">
          {toggle}
          <Link
            href={`/corporate/employees/${row.account_id}`}
            className="hover:text-primary underline"
          >
            {row.employee_name}
          </Link>
        </span>
      </Td>
      <Td className="px-4 py-3">
        {row.teams.map((team, index) => (
          <span key={team.id}>
            {index > 0 && ", "}
            <Link href={`/corporate/teams/${team.id}`} className="hover:text-primary underline">
              {team.name}
            </Link>
          </span>
        ))}
      </Td>
    </>
  );
  if (rows.length === 1) {
    return (
      <Tr>
        {personCells(first)}
        {deviceCells(first, view, period, t, evaluatedAt, locale)}
      </Tr>
    );
  }
  const latest = rows.reduce((best, row) =>
    (row.last_heartbeat_at ?? "") > (best.last_heartbeat_at ?? "") ? row : best,
  );
  const worst = rows.reduce((a, b) => (SEVERITY[a.status] <= SEVERITY[b.status] ? a : b));
  return (
    <Fragment>
      <Tr>
        {personCells(
          first,
          <button
            type="button"
            aria-expanded={expanded}
            aria-label={expanded ? t("collapseDevices") : t("expandDevices")}
            className="focus-visible:ring-ring text-muted-foreground hover:text-foreground rounded-sm focus-visible:ring-2"
            onClick={onToggle}
          >
            <Icon name={expanded ? "chevronDown" : "chevronRight"} size="sm" />
          </button>,
        )}
        <Td className="px-4 py-3">{t("devices", { count: rows.length })}</Td>
        {view === "history" && <Td className="text-muted-foreground px-4 py-3">—</Td>}
        <Td
          className="px-4 py-3"
          title={latest.last_heartbeat_at ? utcDateTime(latest.last_heartbeat_at) : undefined}
        >
          {relativeTime(latest.last_heartbeat_at, evaluatedAt, locale, t("never"))}
        </Td>
        <Td className="px-4 py-3">
          {view === "history" ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            <Badge variant={BADGES[worst.status]}>● {t(worst.status)}</Badge>
          )}
        </Td>
      </Tr>
      {expanded &&
        rows.map((row) => (
          <Tr key={row.device_id} className="bg-muted/30">
            <Td className="px-4 py-3" />
            <Td className="px-4 py-3" />
            {deviceCells(row, view, period, t, evaluatedAt, locale)}
          </Tr>
        ))}
    </Fragment>
  );
}
