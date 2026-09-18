"use client";

import { useState, useTransition } from "react";
import { useFormatter, useTranslations } from "next-intl";

import { corporateAuditExportAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";
import type { CorporateAuditFilterValues } from "@/lib/api/corporate";

import type { CorporateAuditExport, CorporateAuditList } from "@/lib/api/generated/types.gen";

type Props = {
  organizationId: string;
  audit: CorporateAuditList;
  members?: readonly { account_id: string; display_name: string | null }[];
  filters?: CorporateAuditFilterValues;
  labels: {
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
};

type ExportFormat = "json" | "csv";
type ExportRange = "current" | "today" | "last7" | "last30" | "all";

// eslint-disable-next-line max-lines-per-function -- journal rendering and export controls share one action state.
export function CorporateAuditPanel({
  organizationId,
  audit,
  labels,
  members = [],
  filters = {},
}: Props) {
  const t = useTranslations("corporate.auditUi");
  const formatDate = useFormatter();
  const actors = new Map(
    members
      .filter((member) => member.display_name)
      .map((member) => [member.account_id, member.display_name]),
  );
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [exportFormat, setExportFormat] = useState<ExportFormat>("json");
  const [range, setRange] = useState<ExportRange>("current");

  function exportAudit() {
    setMessage(null);
    startTransition(async () => {
      try {
        const result = await corporateAuditExportAction(
          organizationId,
          exportFiltersForRange(filters, range),
        );
        if (!result.ok) {
          setMessage(result.message || labels.failed);
          return;
        }
        const blob = new Blob(
          [
            exportFormat === "csv"
              ? auditExportCsv(result.data)
              : JSON.stringify(result.data, null, 2),
          ],
          {
            type: exportFormat === "csv" ? "text/csv;charset=utf-8" : "application/json",
          },
        );
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${organizationId}-audit.${exportFormat}`;
        link.click();
        URL.revokeObjectURL(url);
      } catch {
        setMessage(labels.failed);
      }
    });
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-medium">{labels.title}</h2>
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground block">{labels.exportFormat}</span>
            <select
              aria-label={labels.exportFormat}
              value={exportFormat}
              onChange={(event) => {
                setExportFormat(event.target.value as ExportFormat);
              }}
              className="border-input bg-background min-h-11 rounded-sm border px-3 text-sm"
            >
              <option value="json">{labels.json}</option>
              <option value="csv">{labels.csv}</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground block">{labels.exportRange}</span>
            <select
              aria-label={labels.exportRange}
              value={range}
              onChange={(event) => {
                setRange(event.target.value as ExportRange);
              }}
              className="border-input bg-background min-h-11 rounded-sm border px-3 text-sm"
            >
              <option value="current">{labels.currentFilters}</option>
              <option value="today">{labels.today}</option>
              <option value="last7">{labels.last7Days}</option>
              <option value="last30">{labels.last30Days}</option>
              <option value="all">{labels.allEvents}</option>
            </select>
          </label>
          <Button type="button" disabled={busy} onClick={exportAudit}>
            {busy ? labels.exporting : labels.export}
          </Button>
        </div>
      </div>
      {audit.items.length ? (
        <ol className="divide-border divide-y text-sm">
          {audit.items.map((item) => (
            <li key={item.audit_id} className="grid gap-1 py-3 sm:grid-cols-[1fr_auto]">
              <span>
                <strong className="font-medium">{auditActionLabel(item.action, t)}</strong>
                <span className="text-muted-foreground">
                  {" "}
                  ·{" "}
                  {item.outcome === "succeeded"
                    ? t("outcomes.succeeded")
                    : item.outcome === "denied"
                      ? t("outcomes.denied")
                      : t("outcomes.failed")}
                </span>
              </span>
              <time className="text-muted-foreground" dateTime={item.created_at}>
                {formatDate.dateTime(new Date(item.created_at), {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}
              </time>
              <span className="text-muted-foreground sm:col-span-2">
                {item.actor_type === "user" &&
                item.actor_account_id &&
                actors.has(item.actor_account_id) ? (
                  <Link
                    href={`/corporate/employees/${item.actor_account_id}`}
                    className="underline underline-offset-4"
                  >
                    {actors.get(item.actor_account_id)}
                  </Link>
                ) : (
                  t(`actors.${item.actor_type}`)
                )}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-muted-foreground text-sm">{labels.noAudit}</p>
      )}
      {message ? (
        <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
          {message}
        </p>
      ) : null}
    </section>
  );
}

function exportFiltersForRange(
  filters: CorporateAuditFilterValues,
  range: ExportRange,
): CorporateAuditFilterValues {
  if (range === "current") return filters;
  const next = { ...filters };
  if (range === "all") {
    delete next.created_from;
    delete next.created_to;
    return next;
  }
  const now = new Date();
  const from = new Date(now);
  from.setUTCDate(from.getUTCDate() - (range === "today" ? 0 : range === "last7" ? 6 : 29));
  return {
    ...next,
    created_from: from.toISOString().slice(0, 10),
    created_to: now.toISOString().slice(0, 10),
  };
}

export function auditExportCsv(data: CorporateAuditExport): string {
  const columns = [
    "audit_id",
    "created_at",
    "actor_type",
    "actor_account_id",
    "action",
    "outcome",
    "target_table",
    "target_id",
    "reason",
    "request_id",
    "payload",
  ] as const;
  const row = (item: CorporateAuditExport["items"][number]) =>
    columns
      .map((column) => csvCell(column === "payload" ? JSON.stringify(item.payload) : item[column]))
      .join(",");
  return [columns.join(","), ...data.items.map(row)].join("\r\n");
}

function csvCell(value: unknown): string {
  const text =
    value === null || value === undefined
      ? ""
      : typeof value === "string"
        ? value
        : typeof value === "number" || typeof value === "boolean"
          ? value.toString()
          : JSON.stringify(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function auditActionLabel(action: string, t: ReturnType<typeof useTranslations>) {
  const parts = action.split(".");
  const entity = parts[0] ?? "";
  const operation = parts.at(-1) ?? "";
  if (action === "member.profile.update") return t("profileUpdated");
  if (
    ![
      "member",
      "team",
      "project",
      "role",
      "binding",
      "service_principal",
      "catalog_assignment",
      "audit",
      "organization",
      "corporate",
    ].includes(entity)
  )
    return t("otherEvent");
  if (
    ![
      "create",
      "update",
      "delete",
      "read",
      "list",
      "write",
      "export",
      "lifecycle",
      "bootstrap",
      "replay",
    ].includes(operation)
  )
    return t("otherEvent");
  return t("event", {
    entity: t(`entities.${entity}`),
    operation: t(`operations.${operation}`),
  });
}
