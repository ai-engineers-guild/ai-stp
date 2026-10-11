import { getTranslations } from "next-intl/server";
import { Link } from "@/lib/i18n/navigation";
import type { RuntimeUsageObjectRow, RuntimeUsageReport } from "@/lib/api/generated/types.gen";
import type { DisplayRow } from "./usage-report-data";
import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";

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
      <Tr key="direct-components" className="bg-muted/30 border-t border-b-0">
        <Th colSpan={7} className="text-foreground font-medium">
          {t("directComponents")}
        </Th>
      </Tr>
    );
  }
  return (
    <Tr
      key={`${entry.row.object_kind}:${entry.row.stable_id}:${entry.row.version}:${entry.row.parent_setup_stable_id ?? ""}`}
      className="border-t border-b-0"
    >
      <Td>
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
      </Td>
      <Td>{entry.row.assigned_to}</Td>
      <Td>
        {entry.row.installed_for}
        {employeeId && (
          <span className="text-muted-foreground block text-xs">
            {entry.row.installation_state ?? t("unknown")}
          </span>
        )}
      </Td>
      <Td>{entry.row.used_by}</Td>
      <Td>
        <Link className="text-primary hover:underline" href={objectDetailHref(entry.row)}>
          {entry.row.uses}
        </Link>
      </Td>
      <Td>{entry.row.active_days}</Td>
      <Td>{entry.row.last_used_at ?? t("noRecordedUseInPeriod")}</Td>
    </Tr>
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
    <Tr key={row.employee_id} className="border-t border-b-0">
      <Td>
        <Link className="text-primary hover:underline" href={employeeHref(row.employee_id)}>
          {row.name ?? row.employee_id}
        </Link>
      </Td>
      <Td>{row.team_ids.map((id) => teamNames.get(id) ?? id).join(", ") || "—"}</Td>
      <Td>
        {row.assigned_components} / {row.installed_components} / {row.used_components}
        <span className="text-muted-foreground block text-xs">
          {!inventoryScanEnabled ? t("scanOff") : (inventory?.coverage ?? t("notScanned"))}
        </span>
      </Td>
      <Td>
        <Link
          className="text-primary hover:underline"
          href={detailHref({ employee_id: row.employee_id, detail_page: "" })}
        >
          {row.uses}
        </Link>
      </Td>
      <Td>{row.active_days}</Td>
      <Td>{row.last_used_at ?? t("noRecordedUseInPeriod")}</Td>
    </Tr>
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
        <Table className="text-left">
          <THead className="bg-muted/40">
            <Tr className="border-b-0">
              {headings.map(({ headingKey, key }) => (
                <Th key={headingKey}>
                  {key ? (
                    <Link href={sortHref(key)} className="hover:text-primary">
                      {t(headingKey)}
                      {sort === key ? (order === "desc" ? " ↓" : " ↑") : ""}
                    </Link>
                  ) : (
                    t(headingKey)
                  )}
                </Th>
              ))}
            </Tr>
          </THead>
          <TBody>
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
          </TBody>
        </Table>
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
