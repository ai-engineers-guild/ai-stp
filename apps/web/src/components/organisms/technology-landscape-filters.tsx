"use client";

import { useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Select } from "@/components/atoms/select";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/atoms/dialog";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { Link, useRouter } from "@/lib/i18n/navigation";
import type { CorporateContext, CategoryView } from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";
import { useTechnologyTaxonomy } from "@/lib/technology-taxonomy";

export function TechnologyLandscapeFilters({
  filters,
  context,
  categories = [],
  launch,
}: {
  filters: Record<string, string | string[]>;
  context: CorporateContext;
  categories?: CategoryView[];
  launch?: ReactNode;
}) {
  const t = useTranslations("technology");
  const w = useTranslations("technology.workspace");
  const router = useRouter();
  const [advanced, setAdvanced] = useState(false);
  const selected = [filters.project_ids ?? filters.project_id ?? []].flat();
  function update(key: string, values: string[]) {
    const query = new URLSearchParams();
    for (const [name, value] of Object.entries(filters))
      for (const entry of [value].flat()) query.append(name, entry);
    query.delete(key);
    if (key === "project_ids") query.delete("project_id");
    query.delete("offset");
    for (const value of values) if (value) query.append(key, value);
    router.push(`/corporate/technology-landscape?${query}`);
  }
  const view = filters.view === "table" ? "table" : "grouped";
  return (
    <>
      <div className="technology-toolbar">
        <Select
          aria-label={w("organization")}
          value={context.organization.organization_id}
          onChange={() => {}}
        >
          <option value={context.organization.organization_id}>{w("allOrganization")}</option>
        </Select>
        <SearchableMultiSelect
          name="project_ids"
          label={w("allProjects")}
          searchLabel={w("searchProject")}
          options={context.projects.map((p) => ({ value: p.project_id, label: p.name }))}
          selected={selected}
          onChange={(values) => {
            update("project_ids", values);
          }}
          modal
          closeLabel={t("close")}
          emptyHint={w("allProjects")}
        />
        <form
          className="technology-search"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            update("query", [data.get("query") as string]);
          }}
        >
          <Button type="submit" size="icon" variant="ghost" aria-label={t("search")}>
            <Icon name="search" size="sm" />
          </Button>
          <Input
            name="query"
            aria-label={t("search")}
            placeholder={w("searchTechnology")}
            defaultValue={typeof filters.query === "string" ? filters.query : ""}
            maxLength={200}
          />
        </form>
        <Button
          variant="outline"
          onClick={() => {
            setAdvanced(true);
          }}
        >
          <Icon name="filter" size="sm" />
          {t("filters")}
        </Button>
        <div className="technology-view-switch" aria-label={t("view")}>
          <Button asChild variant="ghost" className={view === "grouped" ? "technology-active" : ""}>
            <Link
              href={viewHref(filters, "grouped")}
              aria-current={view === "grouped" ? "page" : undefined}
            >
              <Icon name="cards" size="sm" />
              {w("map")}
            </Link>
          </Button>
          <Button asChild variant="ghost" className={view === "table" ? "technology-active" : ""}>
            <Link
              href={viewHref(filters, "table")}
              aria-current={view === "table" ? "page" : undefined}
            >
              <Icon name="list" size="sm" />
              {w("table")}
            </Link>
          </Button>
        </div>
        {launch}
      </div>
      <TechnologyLandscapeAdvanced
        filters={filters}
        context={context}
        categories={categories}
        advanced={advanced}
        setAdvanced={setAdvanced}
      />
    </>
  );
}

function viewHref(filters: Record<string, string | string[]>, next: string) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters))
    for (const item of [value].flat()) query.append(key, item);
  query.set("view", next);
  query.delete("offset");
  return `/corporate/technology-landscape?${query}`;
}

function TechnologyLandscapeAdvanced({
  filters,
  context,
  categories,
  advanced,
  setAdvanced,
}: {
  filters: Record<string, string | string[]>;
  context: CorporateContext;
  categories: CategoryView[];
  advanced: boolean;
  setAdvanced: (open: boolean) => void;
}) {
  const t = useTranslations("technology"),
    w = useTranslations("technology.workspace"),
    router = useRouter();
  const localize = useTechnologyTaxonomy();
  return (
    <Dialog open={advanced} onOpenChange={setAdvanced}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogTitle>{t("filters")}</DialogTitle>
        <DialogDescription>{w("filterDescription")}</DialogDescription>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const query = new URLSearchParams();
            for (const [key, value] of Object.entries(filters))
              for (const item of [value].flat()) query.append(key, item);
            for (const [key, value] of new FormData(event.currentTarget)) {
              query.delete(key);
              if (key === "project_ids") query.delete("project_id");
              if (typeof value === "string" && value) query.set(key, value);
            }
            query.delete("offset");
            router.push(`/corporate/technology-landscape?${query}`);
            setAdvanced(false);
          }}
          className="space-y-4"
        >
          {Object.entries({
            category_id: categories.map((c) => ({ value: c.category_id, label: localize(c).name })),
            team_id: context.teams.map((c) => ({ value: c.team_id, label: c.name })),
            review: ["proposed", "confirmed", "rejected", "overridden"].map((value) => ({
              value,
              label: t(`values.${value}`),
            })),
            context: ["production", "development", "testing", "browser_support"].map((value) => ({
              value,
              label: t(`values.${value}`),
            })),
            freshness: ["current", "stale", "absent", "unknown"].map((value) => ({
              value,
              label: t(`values.${value}`),
            })),
            adoption: ["adopt", "trial", "assess", "hold"].map((value) => ({
              value,
              label: t(`values.${value}`),
            })),
            lifecycle: ["draft", "active", "deprecated", "archived"].map((value) => ({
              value,
              label: t(`values.${value}`),
            })),
          }).map(([name, options]) => (
            <div key={name} className="space-y-2">
              <Label htmlFor={`landscape-${name}`}>
                {t(name === "category_id" ? "category" : name === "team_id" ? "team" : name)}
              </Label>
              <Select
                id={`landscape-${name}`}
                name={name}
                defaultValue={typeof filters[name] === "string" ? filters[name] : ""}
              >
                <option value="">{t("all")}</option>
                {options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            </div>
          ))}
          <Button type="submit">{t("apply")}</Button>
          <Button asChild variant="outline">
            <Link href="/corporate/technology-landscape">{t("reset")}</Link>
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
