"use client";

import type { useFormatter, useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import {
  PeopleSelect,
  PeopleTable,
  PersonIdentity,
  peopleCellClass,
  peopleHeadClass,
} from "@/components/molecules/people-ui";
import type { CorporateAuditFilterValues } from "@/lib/api/corporate-audit";
import { auditActionLabel } from "@/lib/audit-labels";
import { Icon } from "@/theme";

import type { CorporateAuditList } from "@/lib/api/generated/types.gen";

export type AuditEntry = CorporateAuditList["items"][number];

export type AuditMember = {
  account_id: string;
  display_name: string | null;
  contact_email?: string | null;
};

export type AuditLabels = {
  title: string;
  export: string;
  exporting: string;
  exportFormat: string;
  exportRange: string;
  currentFilters: string;
  today: string;
  last7Days: string;
  last30Days: string;
  allEvents: string;
  json: string;
  csv: string;
  noAudit: string;
  failed: string;
};

export type ExportFormat = "json" | "csv";
export type ExportRange = "current" | "today" | "last7" | "last30" | "all";

type T = ReturnType<typeof useTranslations>;

const ACTION_OPTION_LIMIT = 40;
const TARGET_OPTION_LIMIT = 40;

export function outcomeVariant(outcome: string) {
  return outcome === "succeeded" ? "success" : outcome === "denied" ? "warning" : "destructive";
}

function actionOptions(items: readonly AuditEntry[]): string[] {
  const known = new Set(items.map((item) => item.action));
  return [...known].sort().slice(0, ACTION_OPTION_LIMIT);
}

function targetOptions(items: readonly AuditEntry[], t: T): { value: string; label: string }[] {
  const known = [...new Set(items.map((item) => item.target_table))].sort();
  return known.slice(0, TARGET_OPTION_LIMIT).map((table) => ({
    value: table,
    label: t.has(`targets.${table}`) ? t(`targets.${table}`) : table,
  }));
}

export function targetLabel(table: string, t: T) {
  return t.has(`targets.${table}`) ? t(`targets.${table}`) : table;
}

export function AuditToolbar({
  draft,
  members,
  items,
  t,
  onFilter,
  onQuery,
  onReset,
}: {
  draft: CorporateAuditFilterValues;
  members: readonly AuditMember[];
  items: readonly AuditEntry[];
  t: T;
  onFilter: (name: keyof CorporateAuditFilterValues, value: string) => void;
  onQuery: (value: string) => void;
  onReset: () => void;
}) {
  return (
    <div className="border-border bg-card space-y-3 rounded-lg border p-4 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-0 flex-1 sm:min-w-60">
          <Icon
            name="search"
            size="sm"
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 -translate-y-1/2"
          />
          <Input
            type="search"
            aria-label={t("search")}
            placeholder={t("search")}
            value={draft.q ?? ""}
            autoComplete="off"
            className="h-11 pl-10"
            onChange={(event) => {
              onQuery(event.target.value);
            }}
          />
        </div>
        <div className="flex items-center gap-2">
          <Input
            type="date"
            aria-label={t("from")}
            value={draft.created_from ?? ""}
            className="h-11 w-40"
            onChange={(event) => {
              onFilter("created_from", event.target.value);
            }}
          />
          <span aria-hidden className="text-muted-foreground">
            —
          </span>
          <Input
            type="date"
            aria-label={t("to")}
            value={draft.created_to ?? ""}
            className="h-11 w-40"
            onChange={(event) => {
              onFilter("created_to", event.target.value);
            }}
          />
        </div>
        <Button type="button" variant="outline" onClick={onReset}>
          {t("reset")}
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(
          [
            {
              name: "actor_account_id",
              label: t("allActors"),
              options: members
                .filter((member) => member.display_name)
                .map((member) => ({
                  value: member.account_id,
                  label: member.display_name ?? member.account_id,
                })),
            },
            {
              name: "action",
              label: t("allActions"),
              options: actionOptions(items).map((action) => ({
                value: action,
                label: auditActionLabel(action, t),
              })),
            },
            {
              name: "target_table",
              label: t("allTypes"),
              options: targetOptions(items, t),
            },
            {
              name: "outcome",
              label: t("allOutcomes"),
              options: (["succeeded", "denied", "failed"] as const).map((outcome) => ({
                value: outcome,
                label: t(`outcomes.${outcome}`),
              })),
            },
          ] satisfies {
            name: keyof CorporateAuditFilterValues;
            label: string;
            options: { value: string; label: string }[];
          }[]
        ).map((select) => (
          <PeopleSelect
            key={select.name}
            label={select.label}
            value={draft[select.name] ?? ""}
            options={select.options}
            onChange={(value) => {
              onFilter(select.name, value);
            }}
          />
        ))}
      </div>
    </div>
  );
}

function AuditRow({
  item,
  actor,
  selected,
  t,
  formatDate,
  onSelect,
}: {
  item: AuditEntry;
  actor: AuditMember | undefined;
  selected: boolean;
  t: T;
  formatDate: ReturnType<typeof useFormatter>;
  onSelect: (item: AuditEntry) => void;
}) {
  return (
    <tr
      data-selected={selected || undefined}
      className={`border-border hover:bg-muted/20 border-t transition-colors last:border-0 ${
        selected ? "bg-muted/40" : ""
      }`}
    >
      <td className={`${peopleCellClass} text-muted-foreground whitespace-nowrap tabular-nums`}>
        <time dateTime={item.created_at}>
          {formatDate.dateTime(new Date(item.created_at), {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </time>
      </td>
      <td className={`${peopleCellClass} max-w-56`}>
        <button
          type="button"
          onClick={() => {
            onSelect(item);
          }}
          className="focus-visible:ring-ring rounded-sm text-left focus-visible:ring-2 focus-visible:outline-none"
        >
          {item.actor_type === "user" && actor ? (
            <PersonIdentity
              name={actor.display_name ?? item.actor_account_id ?? ""}
              email={actor.contact_email ?? undefined}
            />
          ) : (
            t(`actors.${item.actor_type}`)
          )}
        </button>
      </td>
      <td className={`${peopleCellClass} max-w-64`}>
        <span className="line-clamp-1">{auditActionLabel(item.action, t)}</span>
      </td>
      <td className={`${peopleCellClass} max-w-56`}>
        <span className="line-clamp-1">{targetLabel(item.target_table, t)}</span>
        <span className="text-muted-foreground mt-0.5 block truncate font-mono text-xs">
          {item.target_id}
        </span>
      </td>
      <td className={peopleCellClass}>
        <Badge variant={outcomeVariant(item.outcome)} className="font-sans font-normal">
          {t(`outcomes.${item.outcome}`)}
        </Badge>
      </td>
      <td className={`${peopleCellClass} text-muted-foreground max-w-64`}>
        <span className="line-clamp-1">{item.reason ?? "—"}</span>
      </td>
      <td className="px-2 text-right">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("openEvent", { id: item.audit_id })}
          onClick={() => {
            onSelect(item);
          }}
        >
          <Icon name="chevronRight" size="sm" />
        </Button>
      </td>
    </tr>
  );
}

export function AuditTableView({
  audit,
  actors,
  selected,
  t,
  formatDate,
  noAudit,
  onSelect,
}: {
  audit: CorporateAuditList;
  actors: Map<string, AuditMember>;
  selected: AuditEntry | null;
  t: T;
  formatDate: ReturnType<typeof useFormatter>;
  noAudit: string;
  onSelect: (item: AuditEntry) => void;
}) {
  return (
    <PeopleTable label={t("auditTable")} minWidth="min-w-[60rem]">
      <thead>
        <tr className="border-border border-b">
          {[t("timestamp"), t("actor"), t("action"), t("target"), t("outcome"), t("details")].map(
            (label) => (
              <th key={label} scope="col" className={peopleHeadClass}>
                {label}
              </th>
            ),
          )}
          <th className="relative w-11" scope="col">
            <span className="sr-only">{t("eventDetails")}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {audit.items.map((item) => (
          <AuditRow
            key={item.audit_id}
            item={item}
            actor={item.actor_account_id !== null ? actors.get(item.actor_account_id) : undefined}
            selected={selected?.audit_id === item.audit_id}
            t={t}
            formatDate={formatDate}
            onSelect={onSelect}
          />
        ))}
        {!audit.items.length ? (
          <tr>
            <td colSpan={7} className="text-muted-foreground py-14 text-center text-sm">
              {noAudit}
            </td>
          </tr>
        ) : null}
      </tbody>
    </PeopleTable>
  );
}

export function AuditExportControls({
  busy,
  format,
  range,
  labels,
  onFormat,
  onRange,
  onExport,
}: {
  busy: boolean;
  format: ExportFormat;
  range: ExportRange;
  labels: AuditLabels;
  onFormat: (format: ExportFormat) => void;
  onRange: (range: ExportRange) => void;
  onExport: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        aria-label={labels.exportFormat}
        value={format}
        onChange={(event) => {
          onFormat(event.target.value as ExportFormat);
        }}
        className="border-input bg-background h-11 rounded-sm border px-3 text-sm"
      >
        <option value="json">{labels.json}</option>
        <option value="csv">{labels.csv}</option>
      </select>
      <select
        aria-label={labels.exportRange}
        value={range}
        onChange={(event) => {
          onRange(event.target.value as ExportRange);
        }}
        className="border-input bg-background h-11 rounded-sm border px-3 text-sm"
      >
        <option value="current">{labels.currentFilters}</option>
        <option value="today">{labels.today}</option>
        <option value="last7">{labels.last7Days}</option>
        <option value="last30">{labels.last30Days}</option>
        <option value="all">{labels.allEvents}</option>
      </select>
      <Button type="button" variant="outline" disabled={busy} onClick={onExport}>
        <Icon name="download" size="sm" aria-hidden />
        {busy ? labels.exporting : labels.export}
      </Button>
    </div>
  );
}
