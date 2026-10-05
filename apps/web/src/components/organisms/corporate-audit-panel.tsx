"use client";

import { useCallback, useEffect, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";

import { corporateAuditExportAction } from "@/actions/corporate";
import {
  AuditExportControls,
  AuditTableView,
  AuditToolbar,
  type AuditEntry,
  type AuditLabels,
  type AuditMember,
  type ExportFormat,
  type ExportRange,
} from "@/components/organisms/corporate-audit-ui";
import { AuditDrawer } from "@/components/organisms/corporate-audit-drawer";
import { PeoplePager } from "@/components/organisms/corporate-people-ui";
import type { CorporateAuditFilterValues } from "@/lib/api/corporate-audit";
import { AUDIT_PAGE_SIZES } from "@/lib/page-window";
import { usePathname, useRouter } from "@/lib/i18n/navigation";

import type { CorporateAuditExport, CorporateAuditList } from "@/lib/api/generated/types.gen";

// A shared default keeps the filters-sync branch stable: a per-render `{}`
// literal would change identity every render and loop `setDraft` forever.
const EMPTY_FILTERS: CorporateAuditFilterValues = {};

type Props = {
  organizationId: string;
  audit: CorporateAuditList;
  canExport?: boolean;
  members?: readonly AuditMember[];
  filters?: CorporateAuditFilterValues;
  page?: number;
  pageSize?: number;
  labels: AuditLabels;
};

function useAuditExport(
  organizationId: string,
  filters: CorporateAuditFilterValues,
  failed: string,
) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [exportFormat, setExportFormat] = useState<ExportFormat>("json");
  const [range, setRange] = useState<ExportRange>("current");

  function exportAudit() {
    setMessage(null);
    setBusy(true);
    void (async () => {
      try {
        const result = await corporateAuditExportAction(
          organizationId,
          exportFiltersForRange(filters, range),
        );
        if (!result.ok) {
          setMessage(result.message || failed);
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
        document.body.append(link);
        link.click();
        link.remove();
        window.setTimeout(() => {
          URL.revokeObjectURL(url);
        }, 0);
      } catch {
        setMessage(failed);
      } finally {
        setBusy(false);
      }
    })();
  }

  return { busy, message, exportFormat, range, setExportFormat, setRange, exportAudit };
}

export function CorporateAuditPanel({
  organizationId,
  audit,
  canExport = true,
  labels,
  members = [],
  filters = EMPTY_FILTERS,
  page = 1,
  pageSize = AUDIT_PAGE_SIZES[0],
}: Props) {
  const t = useTranslations("corporate.auditUi");
  const formatDate = useFormatter();
  const router = useRouter();
  const pathname = usePathname();
  const actors = new Map(members.map((member) => [member.account_id, member]));
  const [draft, setDraft] = useState(filters);
  const [applied, setApplied] = useState(filters);
  const [selected, setSelected] = useState<AuditEntry | null>(null);
  const { busy, message, exportFormat, range, setExportFormat, setRange, exportAudit } =
    useAuditExport(organizationId, filters, labels.failed);

  // Adjust the local draft when the server delivers new filters (URL navigation).
  if (applied !== filters) {
    setApplied(filters);
    setDraft(filters);
  }

  const push = useCallback(
    (patch: Record<string, string>) => {
      const params = new URLSearchParams(window.location.search);
      for (const [name, value] of Object.entries(patch)) {
        if (value) params.set(name, value);
        else params.delete(name);
      }
      if (!("page" in patch)) params.delete("page");
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [pathname, router],
  );

  function setFilter(name: keyof CorporateAuditFilterValues, value: string) {
    setDraft((current) => {
      const { [name]: _removed, ...rest } = current;
      void _removed;
      return value ? { ...rest, [name]: value } : rest;
    });
    push({ [name]: value });
  }

  function setQuery(value: string) {
    setDraft((current) => {
      const { q: _removed, ...rest } = current;
      void _removed;
      return value ? { ...rest, q: value } : rest;
    });
  }

  // Free-text search is debounced; selects and dates apply immediately.
  useEffect(() => {
    const next = draft.q ?? "";
    if (next === (filters.q ?? "")) return;
    const timer = window.setTimeout(() => {
      push({ q: next });
    }, 350);
    return () => {
      window.clearTimeout(timer);
    };
  }, [draft.q, filters.q, push]);

  const total = audit.total;
  return (
    <section className="space-y-4" aria-label={labels.title}>
      <AuditToolbar
        draft={draft}
        members={members}
        items={audit.items}
        t={t}
        onFilter={setFilter}
        onQuery={setQuery}
        onReset={() => {
          setDraft(EMPTY_FILTERS);
          router.replace(pathname, { scroll: false });
        }}
      />

      <div className="border-border bg-card rounded-lg border shadow-sm">
        <div className="border-border flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <p className="text-sm font-medium tabular-nums">{t("eventCount", { count: total })}</p>
          {canExport ? (
            <AuditExportControls
              busy={busy}
              format={exportFormat}
              range={range}
              labels={labels}
              onFormat={setExportFormat}
              onRange={setRange}
              onExport={exportAudit}
            />
          ) : null}
        </div>

        <AuditTableView
          audit={audit}
          actors={actors}
          selected={selected}
          t={t}
          formatDate={formatDate}
          noAudit={labels.noAudit}
          onSelect={setSelected}
        />

        <div className="flex flex-wrap items-center justify-between gap-3 px-4">
          <PeoplePager
            kind="events"
            total={total}
            page={page}
            pageSize={pageSize}
            onPage={(next) => {
              push({ page: String(next) });
            }}
          />
          <label className="text-muted-foreground flex items-center gap-2 text-sm">
            {t("rowsPerPage")}
            <select
              value={pageSize}
              aria-label={t("rowsPerPage")}
              className="border-input bg-background h-11 rounded-sm border px-2 text-sm"
              onChange={(event) => {
                push({ size: event.target.value, page: "1" });
              }}
            >
              {AUDIT_PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      {message ? (
        <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
          {message}
        </p>
      ) : null}

      <AuditDrawer
        item={selected}
        actor={selected?.actor_account_id ? actors.get(selected.actor_account_id) : undefined}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      />
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
