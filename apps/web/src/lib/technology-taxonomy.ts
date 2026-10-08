import { useTranslations } from "next-intl";
import type { AreaView, CategoryView, TechnologyView } from "@/lib/api/generated/types.gen";

const legacyCategories = new Set(
  Array.from({ length: 23 }, (_, index) => `category_${String(index + 1).padStart(26, "0")}`),
);

/** Preserve old links; prefer the functional taxonomy in the landscape presentation. */
export function displayCategoryIds(
  technology: TechnologyView,
  categories?: Map<string, CategoryView>,
) {
  const functional = technology.category_ids.filter((id) => {
    const category = categories?.get(id);
    return (
      !legacyCategories.has(id) &&
      !(category?.provenance === "ai_stp:corporate-overview-demo:1" && !category.area_id)
    );
  });
  return functional.length ? functional : technology.category_ids;
}

/** Translate only unchanged default names; tenant edits always display verbatim. */
export function useTechnologyTaxonomy() {
  const t = useTranslations("technology.taxonomy");
  return <T extends AreaView | CategoryView>(record: T): T => {
    const id =
      "area_id" in record && "organization_id" in record ? record.area_id : record.category_id;
    const key = `${id}.name`;
    return t.has(key) && t(key) === record.name ? { ...record, name: t(`${id}.label`) } : record;
  };
}
