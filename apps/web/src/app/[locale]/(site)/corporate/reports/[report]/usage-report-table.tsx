import { getTranslations } from "next-intl/server";
import { Link } from "@/lib/i18n/navigation";
import type { RuntimeUsageObjectRow, RuntimeUsageReport } from "@/lib/api/generated/types.gen";
import type { DisplayRow } from "./usage-report-data";

type TableProps = {
  data: RuntimeUsageReport;
  objectMode: boolean;
  displayRows: DisplayRow[];
  employeeRows: RuntimeUsageReport["employees"];
  employeeId: string;
  expanded: string;
  page: number;
  totalPages: number;
  totalItems: number;
  sort: string;
  order: string;
  teamNames: Map<string, string>;
  inventoryByEmployee: Map<string, RuntimeUsageReport["inventory_employees"][number]>;
  sortHref: (key: string) => string;
  pageHref: (page: number) => string;
  employeeHref: (accountId: string) => string;
  objectDetailHref: (row: RuntimeUsageObjectRow) => string;
  expandHref: (row: RuntimeUsageObjectRow) => string;
  detailHref: (changes: Record<string, string>) => string;
};

type Translator = Awaited<ReturnType<typeof getTranslations<"corporateReports">>>;

const OBJECT_HEADINGS = [
  { headingKey: "tableHeadItem", key: "item" },
  { headingKey: "tableHeadAssignedTo", key: "assigned" },
  { headingKey: "tableHeadInstalledFor", key: "installed" },
  { headingKey: "tableHeadUsedBy", key: "used_by" },
  { headingKey: "tableHeadUses", key: "uses" },
  { headingKey: "tableHeadActiveDays", key: "active_days" },
  { headingKey: "tableHeadLastUsed", key: "last_used" },
] as const;

const EMPLOYEE_HEADINGS = [
  { headingKey: "tableHeadEmployee", key: "employee" },
  { headingKey: "tableHeadTeam", key: "" },
  { headingKey: "tableHeadAssignedInstalledUsed", key: "assigned" },
  { headingKey: "tableHeadUses", key: "uses" },
  { headingKey: "tableHeadActiveDays", key: "active_days" },
  { headingKey: "tableHeadLastUsed", key: "last_used" },
] as const;

function ObjectTableRow({
  entry,
  employeeId,
  expanded,
  objectDetailHref,
  expandHref,
  t,
}: {
  entry: DisplayRow;
  employeeId: string;
  expanded: string;
  objectDetailHref: (row: RuntimeUsageObjectRow) => string;
  expandHref: (row: RuntimeUsageObjectRow) => string;
  t: Translator;
}) {
  if (entry.kind === "direct") {
    return (
      <tr key="direct-components" className="border-border bg-muted/30 border-t">
        <th colSpan={7} className="px-3 py-2 text-left font-medium">
          {t("directComponents")}
        </th>
      </tr>
    );
  }
  return (
    <tr
      key={`${entry.row.object_kind}:${entry.row.stable_id}:${entry.row.version}:${entry.row.parent_setup_stable_id ?? ""}`}
      className="border-border border-t"
    >
      <td className="px-3 py-2">
        {entry.row.parent_setup_stable_id ? <span className="pl-5">↳ </span> : null}
        <Link className="text-primary hover:underline" href={objectDetailHref(entry.row)}>
          {entry.row.name ?? entry.row.stable_id} · {entry.row.version}
        </Link>
        {entry.row.object_kind === "setup" && !employeeId && (
          <Link
            className="text-muted-foreground ml-2 text-xs hover:underline"
            href={expandHref(entry.row)}
          >
            {expanded === `${entry.row.stable_id}@${entry.row.version}`
              ? t("hideComponents")
              : t("showComponents")}
          </Link>
        )}
      </td>
      <td className="px-3 py-2">{entry.row.assigned_to}</td>
      <td className="px-3 py-2">
        {entry.row.installed_for}
        {employeeId && (
          <span className="text-muted-foreground block text-xs">
            {entry.row.installation_state ?? t("unknown")}
          </span>
        )}
      </td>
      <td className="px-3 py-2">{entry.row.used_by}</td>
      <td className="px-3 py-2">
        <Link className="text-primary hover:underline" href={objectDetailHref(entry.row)}>
          {entry.row.uses}
        </Link>
      </td>
      <td className="px-3 py-2">{entry.row.active_days}</td>
      <td className="px-3 py-2">{entry.row.last_used_at ?? t("noRecordedUseInPeriod")}</td>
    </tr>
  );
}

function EmployeeTableRow({
  row,
  teamNames,
  inventoryScanEnabled,
  inventory,
  employeeHref,
  detailHref,
  t,
}: {
  row: RuntimeUsageReport["employees"][number];
  teamNames: Map<string, string>;
  inventoryScanEnabled: boolean;
  inventory?: RuntimeUsageReport["inventory_employees"][number] | undefined;
  employeeHref: (accountId: string) => string;
  detailHref: (changes: Record<string, string>) => string;
  t: Translator;
}) {
  return (
    <tr key={row.employee_id} className="border-border border-t">
      <td className="px-3 py-2">
        <Link className="text-primary hover:underline" href={employeeHref(row.employee_id)}>
          {row.name ?? row.employee_id}
        </Link>
      </td>
      <td className="px-3 py-2">
        {row.team_ids.map((id) => teamNames.get(id) ?? id).join(", ") || "—"}
      </td>
      <td className="px-3 py-2">
        {row.assigned_components} / {row.installed_components} / {row.used_components}
        <span className="text-muted-foreground block text-xs">
          {!inventoryScanEnabled ? t("scanOff") : (inventory?.coverage ?? t("notScanned"))}
        </span>
      </td>
      <td className="px-3 py-2">
        <Link
          className="text-primary hover:underline"
          href={detailHref({ employee_id: row.employee_id, detail_page: "" })}
        >
          {row.uses}
        </Link>
      </td>
      <td className="px-3 py-2">{row.active_days}</td>
      <td className="px-3 py-2">{row.last_used_at ?? t("noRecordedUseInPeriod")}</td>
    </tr>
  );
}

export async function UsageReportTable({
  data,
  objectMode,
  displayRows,
  employeeRows,
  employeeId,
  expanded,
  page,
  totalPages,
  totalItems,
  sort,
  order,
  teamNames,
  inventoryByEmployee,
  sortHref,
  pageHref,
  employeeHref,
  objectDetailHref,
  expandHref,
  detailHref,
}: TableProps) {
  const t = await getTranslations("corporateReports");
  const headings = objectMode ? OBJECT_HEADINGS : EMPLOYEE_HEADINGS;

  return (
    <>
      <div className="border-border overflow-x-auto rounded-lg border">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted/40">
            <tr>
              {headings.map(({ headingKey, key }) => (
                <th key={headingKey} scope="col" className="px-3 py-2">
                  {key ? (
                    <Link href={sortHref(key)} className="hover:text-primary">
                      {t(headingKey)}
                      {sort === key ? (order === "desc" ? " ↓" : " ↑") : ""}
                    </Link>
                  ) : (
                    t(headingKey)
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {objectMode
              ? displayRows.map((entry) => (
                  <ObjectTableRow
                    key={
                      entry.kind === "direct"
                        ? "direct-components"
                        : `${entry.row.object_kind}:${entry.row.stable_id}:${entry.row.version}:${entry.row.parent_setup_stable_id ?? ""}`
                    }
                    entry={entry}
                    employeeId={employeeId}
                    expanded={expanded}
                    objectDetailHref={objectDetailHref}
                    expandHref={expandHref}
                    t={t}
                  />
                ))
              : employeeRows
                  .slice((page - 1) * 10, page * 10)
                  .map((row) => (
                    <EmployeeTableRow
                      key={row.employee_id}
                      row={row}
                      teamNames={teamNames}
                      inventoryScanEnabled={data.inventory_scan_enabled}
                      inventory={inventoryByEmployee.get(row.employee_id)}
                      employeeHref={employeeHref}
                      detailHref={detailHref}
                      t={t}
                    />
                  ))}
          </tbody>
        </table>
        {totalItems === 0 && (
          <p className="text-muted-foreground p-4 text-sm">{t("noMatchingResults")}</p>
        )}
      </div>
      <nav aria-label={t("tablePages")} className="mt-3 flex items-center justify-between text-sm">
        <span className="text-muted-foreground">{t("pageOf", { page, totalPages })}</span>
        <div className="flex gap-3">
          {page > 1 && (
            <Link className="text-primary hover:underline" href={pageHref(page - 1)}>
              {t("pagePrevious")}
            </Link>
          )}
          {page < totalPages && (
            <Link className="text-primary hover:underline" href={pageHref(page + 1)}>
              {t("pageNext")}
            </Link>
          )}
        </div>
      </nav>
    </>
  );
}
