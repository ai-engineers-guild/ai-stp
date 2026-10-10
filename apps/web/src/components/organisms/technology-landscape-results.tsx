"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Menu, MenuTrigger, MenuContent, MenuItem } from "@/components/atoms/menu";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/atoms/dialog";
import { Link } from "@/lib/i18n/navigation";
import type {
  AreaView,
  CategoryView,
  TechnologyLandscapeRow,
  TechnologyLandscapeView,
} from "@/lib/api/generated/types.gen";
import { Icon, type IconName } from "@/theme";
import { displayCategoryIds, useTechnologyTaxonomy } from "@/lib/technology-taxonomy";

const CATEGORY_LIMIT = 5;
const TECHNOLOGY_LIMIT = 5;

function versions(row: TechnologyLandscapeRow) {
  return (
    [
      ...new Set(
        row.projects.flatMap((p) =>
          p.usage.facts
            .filter((f) => f.review !== "rejected" && f.freshness !== "absent")
            .map((f) => f.version)
            .filter(Boolean),
        ),
      ),
    ]
      .sort()
      .join(", ") || "—"
  );
}
const areaIcons: IconName[] = [
  "code",
  "devices",
  "component",
  "link",
  "technology",
  "chart",
  "brain",
  "objects",
  "network",
  "shield",
  "controls",
  "setup",
  "technology",
];

type LandscapeCategoryGroup = {
  key: string;
  name: string;
  rows: TechnologyLandscapeRow[];
};

type LandscapeAreaGroup = {
  key: string;
  name: string;
  areaId: string | null;
  categories: LandscapeCategoryGroup[];
};

function groupLandscape(
  landscape: TechnologyLandscapeView,
  categoryById: Map<string, CategoryView>,
  areaById: Map<string, AreaView>,
  unclassified: string,
): LandscapeAreaGroup[] {
  const groups: LandscapeAreaGroup[] = [];
  const groupByKey = new Map<string, LandscapeAreaGroup>();
  for (const area of [...areaById.values()]
    .filter((area) => area.state !== "archived")
    .sort((left, right) => left.area_id.localeCompare(right.area_id))) {
    const group: LandscapeAreaGroup = {
      key: area.area_id,
      name: area.name,
      areaId: area.area_id,
      categories: [],
    };
    groups.push(group);
    groupByKey.set(area.area_id, group);
  }
  for (const row of landscape.items) {
    const ids = displayCategoryIds(row.technology, categoryById);
    for (const id of ids.length ? ids : [""]) {
      const category = categoryById.get(id);
      const area = category?.area_id ? areaById.get(category.area_id) : undefined;
      let group = groupByKey.get(area?.area_id ?? "unclassified");
      if (!group) {
        group = {
          key: area?.area_id ?? "unclassified",
          name: area?.name ?? unclassified,
          areaId: area?.area_id ?? null,
          categories: [],
        };
        groupByKey.set(group.key, group);
        groups.push(group);
      }
      const ckey = category?.category_id ?? "";
      let bucket = group.categories.find((entry) => entry.key === ckey);
      if (!bucket) {
        bucket = { key: ckey, name: category?.name ?? unclassified, rows: [] };
        group.categories.push(bucket);
      }
      bucket.rows.push(row);
    }
  }
  return groups;
}

function useLandscapePresentation({
  landscape,
  categories = null,
  areas = null,
}: {
  landscape: TechnologyLandscapeView;
  filters: Record<string, string | string[]>;
  categories?: CategoryView[] | null;
  areas?: AreaView[] | null;
}) {
  const t = useTranslations("technology");
  const w = useTranslations("technology.workspace");
  const a = useTranslations("technology.areas");
  const localize = useTechnologyTaxonomy();
  const [active, setActive] = useState<TechnologyLandscapeRow | null>(null);
  const categoryById = new Map(categories?.map((c) => [c.category_id, localize(c)]) ?? []);
  const areaById = new Map(areas?.map((a) => [a.area_id, localize(a)]) ?? []);
  function classification(row: TechnologyLandscapeRow, area: boolean) {
    return (
      [
        ...new Set(
          displayCategoryIds(row.technology, categoryById)
            .map((id) => {
              const c = categoryById.get(id);
              return area ? areaById.get(c?.area_id ?? "")?.name : c?.name;
            })
            .filter(Boolean),
        ),
      ].join(", ") || a("unclassified")
    );
  }
  const groups = groupLandscape(landscape, categoryById, areaById, a("unclassified"));
  return { t, w, active, setActive, classification, groups, landscape };
}

type LandscapeState = ReturnType<typeof useLandscapePresentation>;

export function TechnologyLandscapeResults(props: Parameters<typeof useLandscapePresentation>[0]) {
  const state = useLandscapePresentation(props);
  return (
    <div className="space-y-3">
      <TechnologyLandscapeMap state={state} />
      <TechnologyLandscapeDialog state={state} />
    </div>
  );
}

export function TechnologyLandscapeMap({ state }: { state: LandscapeState }) {
  const { w, groups } = state;
  return (
    <section>
      <h2 className="text-xl font-medium">{w("landscapeHeading")}</h2>
      <p className="text-muted-foreground mb-3 text-sm">{w("landscapeDescription")}</p>
      <div className="technology-map-grid">
        {groups.map((group, index) => (
          <LandscapeAreaCard
            key={group.key}
            group={group}
            icon={areaIcons[index % areaIcons.length] ?? "technology"}
            state={state}
          />
        ))}
      </div>
    </section>
  );
}

function LandscapeAreaCard({
  group,
  icon,
  state,
}: {
  group: LandscapeAreaGroup;
  icon: IconName;
  state: LandscapeState;
}) {
  const { w, setActive } = state;
  const [allCategories, setAllCategories] = useState(false);
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [allTech, setAllTech] = useState<ReadonlySet<string>>(new Set());
  const visible = allCategories ? group.categories : group.categories.slice(0, CATEGORY_LIMIT);
  const hiddenCount = group.categories.length - visible.length;
  function toggleCategory(key: string) {
    setOpen((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }
  function expandAll() {
    setAllCategories(true);
    setOpen(new Set(group.categories.map((category) => category.key)));
  }
  function collapseAll() {
    setAllCategories(false);
    setOpen(new Set());
    setAllTech(new Set());
  }
  return (
    <section className="technology-domain">
      <header>
        <Icon name={icon} />
        <h3>{group.name}</h3>
        <Menu>
          <MenuTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              className="size-7"
              aria-label={w("areaActions")}
            >
              <Icon name="more" size="sm" />
            </Button>
          </MenuTrigger>
          <MenuContent>
            <MenuItem onSelect={expandAll}>{w("expandAll")}</MenuItem>
            <MenuItem onSelect={collapseAll}>{w("collapseAll")}</MenuItem>
            {group.areaId && (
              <MenuItem asChild>
                <Link href={`/corporate/technologies?area_ids=${group.areaId}`}>
                  {w("openTechnologies")}
                </Link>
              </MenuItem>
            )}
          </MenuContent>
        </Menu>
      </header>
      {!group.categories.length && (
        <p className="text-muted-foreground text-xs">{w("emptyArea")}</p>
      )}
      {visible.map((category) => (
        <div key={category.key} className="space-y-1">
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground focus-visible:ring-ring flex min-h-6 w-full items-center gap-1.5 rounded-sm text-left text-xs focus-visible:ring-2 focus-visible:outline-none"
            aria-expanded={open.has(category.key)}
            onClick={() => {
              toggleCategory(category.key);
            }}
          >
            <Icon
              name={open.has(category.key) ? "chevronDown" : "chevronRight"}
              size="sm"
              className="shrink-0"
            />
            <span className="min-w-0 flex-1 truncate">{category.name}</span>
            <Badge variant="secondary" className="shrink-0">
              {category.rows.length}
            </Badge>
          </button>
          {open.has(category.key) && (
            <div className="flex flex-wrap gap-2 pl-4">
              {(allTech.has(category.key)
                ? category.rows
                : category.rows.slice(0, TECHNOLOGY_LIMIT)
              ).map((row) => (
                <Button
                  key={row.technology.technology_id}
                  variant="secondary"
                  className="technology-chip"
                  onClick={() => {
                    setActive(row);
                  }}
                >
                  {row.technology.name}
                </Button>
              ))}
              {category.rows.length > TECHNOLOGY_LIMIT && (
                <Button
                  variant="ghost"
                  className="technology-chip"
                  aria-expanded={allTech.has(category.key)}
                  aria-label={w("moreTechnologies", {
                    count: category.rows.length - TECHNOLOGY_LIMIT,
                  })}
                  onClick={() => {
                    setAllTech((previous) => {
                      const next = new Set(previous);
                      if (next.has(category.key)) next.delete(category.key);
                      else next.add(category.key);
                      return next;
                    });
                  }}
                >
                  {allTech.has(category.key)
                    ? w("showLess")
                    : `+${category.rows.length - TECHNOLOGY_LIMIT}`}
                </Button>
              )}
            </div>
          )}
        </div>
      ))}
      {hiddenCount > 0 ? (
        <Button
          variant="ghost"
          className="technology-chip self-start"
          aria-label={w("moreCategories", { count: hiddenCount })}
          onClick={() => {
            setAllCategories(true);
          }}
        >
          +{hiddenCount}
        </Button>
      ) : allCategories && group.categories.length > CATEGORY_LIMIT ? (
        <Button
          variant="ghost"
          className="technology-chip self-start"
          onClick={() => {
            setAllCategories(false);
          }}
        >
          {w("showLess")}
        </Button>
      ) : null}
    </section>
  );
}

export function TechnologyLandscapeDialog({ state }: { state: LandscapeState }) {
  const { t, w, active, setActive, classification } = state;
  return (
    <Dialog
      open={active !== null}
      onOpenChange={(open) => {
        if (!open) setActive(null);
      }}
    >
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
        <DialogTitle>{active?.technology.name}</DialogTitle>
        <DialogDescription>
          {active?.technology.description || w("technologyUsage")}
        </DialogDescription>
        {active && (
          <>
            <p className="text-sm">
              {classification(active, true)} / {classification(active, false)}
            </p>
            <p className="text-sm">
              {w("versions")}: {versions(active)}
            </p>
            <ul className="divide-border divide-y">
              {active.projects.map((project) => (
                <li key={project.project_id} className="space-y-2 py-3">
                  <Link
                    className="font-medium underline underline-offset-4"
                    href={`/corporate/projects/${project.project_id}`}
                  >
                    {project.name}
                  </Link>
                  {project.usage.facts.map((fact, index) => (
                    <div key={index} className="text-sm">
                      <span>
                        {t(`values.${fact.context}`)} · {fact.version || "—"} ·{" "}
                        {t(`values.${fact.review}`)}
                      </span>
                      <ul className="text-muted-foreground text-xs">
                        {fact.evidence.map((e, i) => (
                          <li key={i}>{e.path ?? e.reference ?? e.source}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </li>
              ))}
            </ul>
            <Button asChild variant="outline">
              <Link href={`/corporate/technologies/${active.technology.technology_id}`}>
                {w("openRegistry")}
              </Link>
            </Button>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
