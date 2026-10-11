"use client";

import { useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { MenuItem } from "@/components/atoms/menu";
import { Select } from "@/components/atoms/select";
import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";
import { PagePager } from "@/components/molecules/page-pager";
import { EntityDetailMenu } from "@/components/organisms/entity-detail-menu";
import type { TechnologyLandscapeRow } from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";
import { versions, type LandscapeState } from "./technology-landscape-state";

export function TechnologyLandscapeTable({ state }: { state: LandscapeState }) {
  const h = useTranslations("hub");
  const { t, w, setActive, sort, setSort, classification, shown, landscape } = state;
  const rowMenu = (row: TechnologyLandscapeRow) => (
    <EntityDetailMenu
      moreLabel={h("moreActions")}
      openLabel={w("openTechnology", { name: row.technology.name })}
      openHref={`/corporate/technologies/${encodeURIComponent(row.technology.technology_id)}`}
      adminItems={
        <MenuItem
          onSelect={() => {
            setActive(row);
          }}
        >
          <Icon name="eye" size="sm" />
          {w("preview")}
        </MenuItem>
      }
    />
  );
  return (
    <section className="technology-summary">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-2xl font-medium">{w("summary")}</h2>
          <p className="text-muted-foreground text-sm">{w("summaryDescription")}</p>
        </div>
        <p className="text-muted-foreground text-xs">
          {w("shown", { count: shown.length, total: landscape.total })}
        </p>
      </div>
      <div
        className="technology-table-frame"
        role="region"
        aria-label={w("summary")}
        // The scroll region must remain keyboard accessible on narrow screens.
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
      >
        <Table>
          <caption className="sr-only">{w("summary")}</caption>
          <THead>
            <Tr>
              {[
                ["name", t("technology")],
                ["area", w("area")],
                ["category", w("category")],
                ["versions", w("versions")],
                ["projects", t("projects")],
                ["status", w("status")],
              ].map(([key, label]) => (
                <Th key={key}>
                  <Button
                    variant="ghost"
                    className="h-auto min-h-8 justify-start p-0 text-xs"
                    onClick={() => {
                      setSort({
                        key: key ?? "name",
                        descending: sort.key === key ? !sort.descending : false,
                      });
                    }}
                  >
                    {label}
                    <Icon name="sort" size="sm" />
                  </Button>
                </Th>
              ))}
              <Th>
                <span className="sr-only">{w("actions")}</span>
              </Th>
            </Tr>
          </THead>
          <TBody>
            {shown.map((row) => (
              <Tr key={row.technology.technology_id}>
                <Td>
                  <Button
                    variant="ghost"
                    className="h-auto min-h-8 p-0 font-medium"
                    onClick={() => {
                      setActive(row);
                    }}
                  >
                    {row.technology.name}
                  </Button>
                </Td>
                <Td>{classification(row, true)}</Td>
                <Td>{classification(row, false)}</Td>
                <Td>{versions(row)}</Td>
                <Td>
                  <Button
                    variant="ghost"
                    className="h-auto min-h-8 p-0"
                    onClick={() => {
                      setActive(row);
                    }}
                  >
                    {row.project_count}
                  </Button>
                </Td>
                <Td>
                  <Badge variant="secondary">
                    {row.technology.lifecycle === "draft"
                      ? w("draft")
                      : row.proposed_project_count
                        ? w("review")
                        : w("standard")}
                  </Badge>
                </Td>
                <Td>{rowMenu(row)}</Td>
              </Tr>
            ))}
          </TBody>
        </Table>
      </div>
      {!shown.length && (
        <p role="status" className="text-muted-foreground p-6 text-sm">
          {t("empty")}
        </p>
      )}
      <TechnologyLandscapePager state={state} />
    </section>
  );
}

function TechnologyLandscapePager({ state }: { state: LandscapeState }) {
  const { t, w, currentPage, totalPages, setPage, size, setSize, landscape } = state;
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
        <div className="flex items-center gap-3 text-sm">
          <span>{w("showPerPage")}</span>
          <Select
            aria-label={w("pageSize")}
            className="w-20"
            value={size}
            onChange={(e) => {
              setSize(Number(e.target.value));
              setPage(1);
            }}
          >
            {[12, 24, 48, 96].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>
          <span>{w("ofTechnologies", { total: landscape.total })}</span>
        </div>
      }
    />
  );
}
