"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import type {
  AreaView,
  CategoryView,
  TechnologyLandscapeRow,
  TechnologyLandscapeView,
} from "@/lib/api/generated/types.gen";
import { displayCategoryIds, useTechnologyTaxonomy } from "@/lib/technology-taxonomy";

export function versions(row: TechnologyLandscapeRow) {
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

export type LandscapeCategoryGroup = {
  key: string;
  name: string;
  rows: TechnologyLandscapeRow[];
};

export type LandscapeAreaGroup = {
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

export function useLandscapePresentation({
  landscape,
  filters,
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
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(12);
  const [sort, setSort] = useState({ key: "name", descending: false });
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
  const sorted = [...landscape.items].sort((a, b) => {
    const value = (row: TechnologyLandscapeRow) =>
      sort.key === "projects"
        ? row.project_count
        : sort.key === "area"
          ? classification(row, true)
          : sort.key === "category"
            ? classification(row, false)
            : sort.key === "versions"
              ? versions(row)
              : sort.key === "status"
                ? row.technology.lifecycle
                : row.technology.name;
    const av = value(a),
      bv = value(b);
    return (
      (typeof av === "number" && typeof bv === "number"
        ? av - bv
        : String(av).localeCompare(String(bv))) * (sort.descending ? -1 : 1)
    );
  });
  const totalPages = Math.max(1, Math.ceil(sorted.length / size));
  const currentPage = Math.min(page, totalPages);
  const shown = sorted.slice((currentPage - 1) * size, currentPage * size);
  return {
    t,
    w,
    active,
    setActive,
    page,
    setPage,
    size,
    setSize,
    sort,
    setSort,
    classification,
    groups,
    sorted,
    totalPages,
    currentPage,
    shown,
    grouped: filters.view !== "table",
    landscape,
  };
}

export type LandscapeState = ReturnType<typeof useLandscapePresentation>;
