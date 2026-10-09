"use client";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Select } from "@/components/atoms/select";

import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";

import { PagePager } from "@/components/molecules/page-pager";

import { Link } from "@/lib/i18n/navigation";
import { Menu, MenuTrigger, MenuContent, MenuItem } from "@/components/atoms/menu";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";

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
    depVisible,
    depRows,
    scan,
    mode,
    search,
    status,
    kind,
    pendingOnly,
    setSearch,
    setStatus,
    setKind,
    setPendingOnly,
    setPage,
  } = state;
  const sectioned = mode === "scan" && depRows.length > 0;
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
            <Label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm whitespace-nowrap">
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
        {sectioned && <h3 className="mb-2 text-base font-medium">{w("sectionTechnologies")}</h3>}
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
                <Th>{w("category")}</Th>
                <Th>{w("area")}</Th>
                <Th>{w("versions")}</Th>
                <Th>{w("evidence")}</Th>
                {mode === "mapping" && <Th>{w("project")}</Th>}
                <Th>
                  <span className="sr-only">{w("actions")}</span>
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
        {sectioned && (
          <section className="mt-6">
            <h3 className="mb-2 text-base font-medium">{w("sectionDependencies")}</h3>
            <div
              className="technology-table-frame"
              role="region"
              aria-label={w("sectionDependencies")}
              // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
              tabIndex={0}
            >
              <Table className="technology-scan-table">
                <caption className="sr-only">{w("sectionDependencies")}</caption>
                <THead>
                  <Tr>
                    <Th>{w("found")}</Th>
                    <Th>{w("category")}</Th>
                    <Th>{w("area")}</Th>
                    <Th>{w("versions")}</Th>
                    <Th>{w("evidence")}</Th>
                    <Th>
                      <span className="sr-only">{w("actions")}</span>
                    </Th>
                  </Tr>
                </THead>
                <TBody>
                  {depVisible.map((row) => (
                    <TechnologyFindingTableRow key={rowKey(row)} state={state} row={row} />
                  ))}
                </TBody>
              </Table>
            </div>
            <TechnologyDependenciesPager state={state} />
          </section>
        )}
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
    t,
    mode,
    canUpdate,
    mutation,
    drafts,
    draft,
    patch,
    areaNames,
    categoryNames,
    setActiveKey,
    setCreate,
    setEvidence,
    apply,
  } = state;
  const value = draft(row);
  const category = categoryNames.get(value.category);
  const needsReview = state.pending(row);
  const openCreate = (kind: "technology" | "category") => {
    setActiveKey(rowKey(row));
    setCreate(kind);
  };
  return (
    <Tr className={needsReview ? "bg-warning/10" : ""}>
      <Td>
        <span className="font-medium">{row.technology_name ?? row.coordinate}</span>
        {needsReview && (
          <span className="text-muted-foreground mt-1 block text-sm">
            {w(`findingState.${findingStatus(row, state.names)}`)}
          </span>
        )}
      </Td>
      <Td>
        <fieldset disabled={!canUpdate || mutation.busy}>
          {category?.state === "archived" ? (
            <span className="text-sm">{category.name}</span>
          ) : (
            <SearchableMultiSelect
              name={`category-${rowKey(row)}`}
              label={`${w("category")}: ${row.technology_name ?? row.coordinate}`}
              searchLabel={w("chooseCategory")}
              options={(state.categories ?? [])
                .filter((item) => item.state === "active")
                .map((item) => ({ value: item.category_id, label: item.name }))}
              selected={value.category ? [value.category] : []}
              multiple={false}
              emptyHint={w("chooseCategory")}
              closeLabel={t("close")}
              onChange={(values) => {
                patch(row, { category: values[0] ?? "", review: "confirmed" });
              }}
            />
          )}
        </fieldset>
      </Td>
      <Td>{areaNames.get(category?.area_id ?? "") ?? "—"}</Td>
      <Td className="text-muted-foreground">{row.version ?? "—"}</Td>
      <Td>
        <Button
          variant="ghost"
          className="min-h-11 p-0 text-left"
          onClick={() => {
            setEvidence(row);
          }}
        >
          {w("evidenceCount", { count: row.evidence.length })}
        </Button>
      </Td>
      {mode === "mapping" && (
        <Td>
          <Link href={`/corporate/projects/${row.scan.project_id}`}>
            {row.scan.project_name ?? row.scan.project_id}
          </Link>
        </Td>
      )}
      <Td>
        <div className="flex items-center gap-1">
          {canUpdate && drafts[rowKey(row)] && (
            <Button
              size="icon"
              variant="outline"
              disabled={mutation.busy || !value.category}
              aria-label={w("confirmApply")}
              onClick={() => {
                apply([row]);
              }}
            >
              <Icon name="check" size="sm" />
            </Button>
          )}
          <Menu>
            <MenuTrigger asChild>
              <Button size="icon" variant="ghost" aria-label={w("actions")}>
                <Icon name="more" size="sm" />
              </Button>
            </MenuTrigger>
            <MenuContent>
              <MenuItem
                onSelect={() => {
                  setEvidence(row);
                }}
              >
                {w("evidence")}
              </MenuItem>
              {canUpdate && (
                <>
                  <MenuItem
                    onSelect={() => {
                      openCreate("category");
                    }}
                  >
                    {t("createCategory")}
                  </MenuItem>
                  <MenuItem
                    onSelect={() => {
                      openCreate("technology");
                    }}
                  >
                    {w("createTechnology")}
                  </MenuItem>
                  <MenuItem
                    disabled={mutation.busy}
                    onSelect={() => {
                      apply([row], true);
                    }}
                  >
                    {w("excludeFinding")}
                  </MenuItem>
                </>
              )}
            </MenuContent>
          </Menu>
        </div>
      </Td>
    </Tr>
  );
}

function TechnologyFindingsPager({ state }: { state: TechnologyReviewState }) {
  const { t, w, currentPage, totalPages, setPage, visible, techRows, size, setSize } = state;
  return (
    <FindingPager
      t={t}
      w={w}
      page={currentPage}
      totalPages={totalPages}
      onPage={setPage}
      shown={visible.length}
      total={techRows.length}
      size={size}
      onSize={(value) => {
        setSize(value);
        setPage(1);
      }}
    />
  );
}

function TechnologyDependenciesPager({ state }: { state: TechnologyReviewState }) {
  const {
    t,
    w,
    depCurrentPage,
    depTotalPages,
    setDepPage,
    depVisible,
    depRows,
    depSize,
    setDepSize,
  } = state;
  return (
    <FindingPager
      t={t}
      w={w}
      page={depCurrentPage}
      totalPages={depTotalPages}
      onPage={setDepPage}
      shown={depVisible.length}
      total={depRows.length}
      size={depSize}
      onSize={(value) => {
        setDepSize(value);
        setDepPage(1);
      }}
    />
  );
}

function FindingPager({
  t,
  w,
  page,
  totalPages,
  onPage,
  shown,
  total,
  size,
  onSize,
}: {
  t: TechnologyReviewState["t"];
  w: TechnologyReviewState["w"];
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
  shown: number;
  total: number;
  size: number;
  onSize: (size: number) => void;
}) {
  return (
    <PagePager
      label={w("pagination")}
      page={page}
      totalPages={totalPages}
      onPage={onPage}
      controls={{
        previous: t("previous"),
        next: t("next"),
        page: (value) => w("page", { page: value }),
      }}
      summary={
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span>{w("shown", { count: shown, total })}</span>
          <Select
            aria-label={w("pageSize")}
            className="w-32"
            value={size}
            onChange={(e) => {
              onSize(Number(e.target.value));
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
