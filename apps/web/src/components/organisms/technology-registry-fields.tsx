"use client";

import { useTranslations } from "next-intl";

import { Input } from "@/components/atoms/input";
import { Select } from "@/components/atoms/select";
import { Label } from "@/components/atoms/label";
import type { AreaView, CategoryView, TechnologyView } from "@/lib/api/generated/types.gen";

export function AreaField({
  prefix,
  areas,
  initial,
}: {
  prefix: string;
  areas: AreaView[];
  initial: CategoryView | undefined;
}) {
  const t = useTranslations("technology");
  const areaT = useTranslations("technology.areas");
  return (
    <div className="space-y-2">
      <Label htmlFor={`${prefix}-area`}>{t("areas.field")}</Label>
      <Select
        id={`${prefix}-area`}
        name="area_id"
        defaultValue={initial?.area_id ?? ""}
        className="border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2"
      >
        <option value="">{areaT("unassigned")}</option>
        {areas.map((area) => (
          <option key={area.area_id} value={area.area_id}>
            {area.name}
          </option>
        ))}
      </Select>
    </div>
  );
}

export function CategoryStateField({ prefix }: { prefix: string }) {
  const t = useTranslations("technology");
  return (
    <div className="space-y-2">
      <Label htmlFor={`${prefix}-state`}>{t("categoryState")}</Label>
      <Select
        id={`${prefix}-state`}
        name="state"
        defaultValue="active"
        className="border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2"
      >
        <option value="active">{t("values.active")}</option>
        <option value="draft">{t("values.draft")}</option>
      </Select>
    </div>
  );
}

export function TechnologyFields({
  prefix,
  categories,
  initial,
}: {
  prefix: string;
  categories: CategoryView[] | null;
  initial: TechnologyView | undefined;
}) {
  const t = useTranslations("technology");
  return (
    <>
      {categories === null ? (
        <div className="space-y-2">
          <Label htmlFor={`${prefix}-categories`}>{t("knownCategories")}</Label>
          <Input
            id={`${prefix}-categories`}
            name="category_ids"
            required
            defaultValue={initial?.category_ids.join(" ")}
          />
        </div>
      ) : (
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">{t("categories")}</legend>
          {categories.map((category) => (
            <label key={category.category_id} className="flex min-h-11 items-center gap-3">
              <input
                type="checkbox"
                name="category_ids"
                value={category.category_id}
                defaultChecked={initial?.category_ids.includes(category.category_id)}
                className="accent-primary h-4 w-4"
              />
              {category.name}
            </label>
          ))}
          {categories.length === 0 && (
            <p className="text-muted-foreground text-sm">{t("categoryRequired")}</p>
          )}
        </fieldset>
      )}
      <div className="space-y-2">
        <Label htmlFor={`${prefix}-aliases`}>{t("aliases")}</Label>
        <textarea
          id={`${prefix}-aliases`}
          name="aliases"
          rows={3}
          defaultValue={initial?.aliases.join("\n")}
          className="border-input bg-background focus-visible:ring-ring w-full rounded-sm border px-3 py-2 text-sm focus-visible:ring-2"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor={`${prefix}-icon`}>{t("iconUrl")}</Label>
        <Input
          id={`${prefix}-icon`}
          name="icon_url"
          type="url"
          maxLength={2048}
          defaultValue={initial?.icon_url ?? ""}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor={`${prefix}-official`}>{t("officialUrls")}</Label>
        <textarea
          id={`${prefix}-official`}
          name="official_urls"
          rows={3}
          defaultValue={initial?.official_urls.join("\n")}
          className="border-input bg-background focus-visible:ring-ring w-full rounded-sm border px-3 py-2 text-sm focus-visible:ring-2"
        />
      </div>
    </>
  );
}
