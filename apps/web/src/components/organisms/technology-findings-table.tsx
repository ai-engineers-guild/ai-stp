"use client";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Select } from "@/components/atoms/select";

import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";

import { PagePager } from "@/components/molecules/page-pager";

import { Link } from "@/lib/i18n/navigation";

import { Icon } from "@/theme";

import {
  findingStatus,
  rowKey,
  type Row,
  type TechnologyReviewState,
} from "@/lib/technology-review-state";
export function TechnologyFindingsTable({ state }: { state: TechnologyReviewState }) {
  const {
    t,
    w,
    s,
    allRows,
    visible,
    scan,
    mode,
    selected,
    search,
    status,
    kind,
    pendingOnly,
    setSearch,
    setStatus,
    setKind,
    setPendingOnly,
    setPage,
    setSelected,
  } = state;
  return (
    <>
      <section className="min-w-0">
        {scan && (
          <div className="technology-filter-bar mb-4">
            <div className="technology-search">
              <Icon name="search" size="sm" />
              <Input
                aria-label={t("search")}
                placeholder={w("searchFindings")}
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
              />
            </div>
            <Select
              aria-label={w("status")}
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">{w("allStatuses")}</option>
              {["open", "candidate", "confirmation", "category", "resolved", "rejected"].map(
                (value) => (
                  <option key={value} value={value}>
                    {w(`findingState.${value}`)}
                  </option>
                ),
              )}
            </Select>
            <Select
              aria-label={w("type")}
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setPage(1);
              }}
            >
              <option value="">{w("allTypes")}</option>
              {[...new Set(allRows.map((r) => r.kind))].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
            <Label className="flex items-center gap-2 text-xs whitespace-nowrap">
              <input
                type="checkbox"
                checked={pendingOnly}
                onChange={(e) => {
                  setPendingOnly(e.target.checked);
                  setPage(1);
                }}
              />
              {w("pendingOnly")}
            </Label>
          </div>
        )}
        <div
          className="technology-table-frame"
          role="region"
          aria-label={s("findings")}
          // The scroll region must remain keyboard accessible on narrow screens.
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
          tabIndex={0}
        >
          <Table
            className={mode === "mapping" ? "technology-mapping-table" : "technology-scan-table"}
          >
            <caption className="sr-only">{s("findings")}</caption>
            <THead>
              <Tr>
                <Th>{w("found")}</Th>
                <Th>{w("suggested")}</Th>
                <Th>{w("classification")}</Th>
                {mode === "mapping" && (
                  <>
                    <Th>{w("project")}</Th>
                    <Th>{w("scan")}</Th>
                  </>
                )}
                {scan && <Th>{w("file")}</Th>}
                <Th>{w("status")}</Th>
                <Th>
                  <input
                    type="checkbox"
                    aria-label={w("selectAll")}
                    checked={
                      visible.length > 0 && visible.every((r) => selected.includes(rowKey(r)))
                    }
                    onChange={(e) => {
                      setSelected(
                        e.target.checked
                          ? [...new Set([...selected, ...visible.map(rowKey)])]
                          : selected.filter((key) => !visible.some((r) => rowKey(r) === key)),
                      );
                    }}
                  />
                </Th>
              </Tr>
            </THead>
            <TBody>
              {visible.map((row) => (
                <TechnologyFindingTableRow key={rowKey(row)} state={state} row={row} />
              ))}
            </TBody>
          </Table>
        </div>
        {!visible.length && (
          <p role="status" className="text-muted-foreground py-8 text-center text-sm">
            {w("noFindings")}
          </p>
        )}
        <TechnologyFindingsPager state={state} />
      </section>
    </>
  );
}

export function TechnologyFindingTableRow({
  state,
  row,
}: {
  state: TechnologyReviewState;
  row: Row;
}) {
  const {
    w,
    names,
    active,
    scan,
    mode,
    selected,
    classification,
    setActiveKey,
    setSelected,
    setEvidence,
  } = state;
  return (
    <Tr
      key={rowKey(row)}
      className={active && rowKey(active) === rowKey(row) ? "technology-selected-row" : ""}
    >
      <Td>
        <Button
          variant="ghost"
          className="h-auto min-h-11 p-0 text-left"
          onClick={() => {
            setActiveKey(rowKey(row));
          }}
        >
          {row.coordinate}
        </Button>
        {row.version && <span className="text-muted-foreground block text-xs">{row.version}</span>}
      </Td>
      <Td>{names.get(row.technology_id ?? row.candidate_technology_id ?? "")?.name ?? "—"}</Td>
      <Td className="max-w-64">{classification(row)}</Td>
      {mode === "mapping" && (
        <>
          <Td>{row.scan.project_name ?? row.scan.project_id}</Td>
          <Td>
            <Link
              className="block truncate text-xs"
              title={row.scan.scan_id}
              href={`/corporate/technology-scans/${row.scan.scan_id}`}
            >
              {row.scan.scan_id}
            </Link>
          </Td>
        </>
      )}
      {scan && (
        <Td>
          <Button
            variant="ghost"
            className="h-auto min-h-11 p-0 text-left text-xs break-all"
            onClick={() => {
              setEvidence(row);
            }}
          >
            {row.evidence[0]?.path ?? row.evidence[0]?.reference ?? "—"}
          </Button>
        </Td>
      )}
      <Td>
        <Badge variant="secondary" className="whitespace-nowrap">
          {w(`findingState.${findingStatus(row, state.names)}`)}
        </Badge>
      </Td>
      <Td>
        <div className="flex items-center gap-1">
          <input
            type="checkbox"
            aria-label={w("selectFinding", { name: row.coordinate })}
            checked={selected.includes(rowKey(row))}
            onChange={(e) => {
              setSelected(
                e.target.checked
                  ? [...selected, rowKey(row)]
                  : selected.filter((key) => key !== rowKey(row)),
              );
            }}
          />
          <Button
            size="icon"
            variant="ghost"
            aria-label={w("inspectFinding", { name: row.coordinate })}
            onClick={() => {
              setActiveKey(rowKey(row));
            }}
          >
            <Icon name="more" size="sm" />
          </Button>
        </div>
      </Td>
    </Tr>
  );
}

function TechnologyFindingsPager({ state }: { state: TechnologyReviewState }) {
  const { t, w, currentPage, totalPages, setPage, visible, rows, size, setSize } = state;
  return (
    <PagePager
      label={w("pagination")}
      page={currentPage}
      totalPages={totalPages}
      onPage={setPage}
      controls={{
        previous: t("previous"),
        next: t("next"),
        page: (value) => w("page", { page: value }),
      }}
      summary={
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span>{w("shown", { count: visible.length, total: rows.length })}</span>
          <Select
            aria-label={w("pageSize")}
            className="w-32"
            value={size}
            onChange={(e) => {
              setSize(Number(e.target.value));
              setPage(1);
            }}
          >
            {[10, 20, 50].map((value) => (
              <option key={value} value={value}>
                {w("perPage", { count: value })}
              </option>
            ))}
          </Select>
        </div>
      }
    />
  );
}
