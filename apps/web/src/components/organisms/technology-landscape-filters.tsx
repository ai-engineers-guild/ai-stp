import { getTranslations } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Link } from "@/lib/i18n/navigation";
import type { CorporateContext } from "@/lib/api/generated/types.gen";

const dimensions = {
  context: ["production", "development", "testing", "browser_support"],
  review: ["proposed", "confirmed", "rejected", "overridden", "retired"],
  freshness: ["current", "stale", "absent", "unknown"],
  lifecycle: ["draft", "active", "deprecated", "archived"],
  adoption: ["none", "assess", "trial", "adopt", "hold"],
} as const;

export async function TechnologyLandscapeFilters({
  filters,
  context,
}: {
  filters: Record<string, string>;
  context: CorporateContext;
}) {
  const t = await getTranslations("technology");
  return (
    <form className="space-y-4" method="get">
      <h2 className="text-xl font-medium">{t("filters")}</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(dimensions).map(([key, values]) => (
          <FilterSelect
            key={key}
            name={key}
            label={t(key)}
            value={filters[key]}
            all={t("all")}
            options={values.map((value) => ({ value, label: t(`values.${value}`) }))}
          />
        ))}
        <FilterSelect
          name="project_id"
          label={t("project")}
          value={filters.project_id}
          all={t("all")}
          options={context.projects.map((p) => ({ value: p.project_id, label: p.name }))}
        />
        <FilterSelect
          name="team_id"
          label={t("team")}
          value={filters.team_id}
          all={t("all")}
          options={context.teams.map((p) => ({ value: p.team_id, label: p.name }))}
        />
        <div className="space-y-2">
          <Label htmlFor="landscape-category">{t("category")}</Label>
          <Input id="landscape-category" name="category_id" defaultValue={filters.category_id} />
        </div>
      </div>
      <div className="flex flex-wrap gap-4">
        {["include_history", "include_inactive"].map((key) => (
          <label key={key} className="flex min-h-11 items-center gap-2">
            <input
              type="checkbox"
              name={key}
              value="true"
              defaultChecked={filters[key] === "true"}
            />
            {t(key === "include_history" ? "history" : "inactive")}
          </label>
        ))}
      </div>
      {filters.technology_id && (
        <input type="hidden" name="technology_id" value={filters.technology_id} />
      )}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" size="lg">
          {t("apply")}
        </Button>
        <Button asChild variant="outline" size="lg">
          <Link href="/corporate/technology-landscape">{t("reset")}</Link>
        </Button>
      </div>
    </form>
  );
}

function FilterSelect({
  name,
  label,
  value,
  all,
  options,
}: {
  name: string;
  label: string;
  value: string | undefined;
  all: string;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={`landscape-${name}`}>{label}</Label>
      <select
        id={`landscape-${name}`}
        name={name}
        defaultValue={value ?? ""}
        className="border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2"
      >
        <option value="">{all}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
