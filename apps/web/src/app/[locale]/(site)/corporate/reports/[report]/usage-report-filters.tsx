import { Select } from "@/components/atoms/select";
import { getTranslations } from "next-intl/server";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import type { CorporateContext } from "@/lib/api/generated/types.gen";

const ADDITIONAL_FILTER_FIELDS = [
  { key: "project_id", labelKey: "filterProjectId" },
  { key: "technology_id", labelKey: "filterTechnologyId" },
  { key: "harness", labelKey: "filterHarness" },
  { key: "device_id", labelKey: "filterDeviceId" },
  { key: "setup_stable_id", labelKey: "filterSetupStableId" },
  { key: "component_stable_id", labelKey: "filterComponentStableId" },
] as const;

type FiltersProps = {
  context: CorporateContext;
  employeeOptions: Map<string, string>;
  selected: (key: string) => string;
  employeeId: string;
  period: string;
  usageState: string;
  view: string;
  chart: string;
  sort: string;
  order: string;
  expanded: string;
};

export async function UsageReportFilters({
  context,
  employeeOptions,
  selected,
  employeeId,
  period,
  usageState,
  view,
  chart,
  sort,
  order,
  expanded,
}: FiltersProps) {
  const t = await getTranslations("corporateReports");

  return (
    <form className="border-border bg-card mb-5 grid gap-3 rounded-lg border p-4 sm:grid-cols-5">
      <SearchableMultiSelect
        name="team_id"
        label={t("filterTeam")}
        searchLabel={t("findTeam")}
        options={context.teams.map((team) => ({ value: team.team_id, label: team.name }))}
        selected={selected("team_id") ? [selected("team_id")] : []}
        multiple={false}
        emptyHint={t("allTeams")}
      />
      <SearchableMultiSelect
        name="employee_id"
        label={t("filterEmployee")}
        searchLabel={t("findEmployee")}
        options={[...employeeOptions].map(([value, label]) => ({ value, label }))}
        selected={employeeId ? [employeeId] : []}
        multiple={false}
        emptyHint={t("allEmployees")}
      />
      <label className="text-sm">
        {t("period")}
        <Select
          name="period"
          defaultValue={period}
          className="border-input bg-background mt-1 w-full rounded-sm border px-2 py-1"
        >
          <option value="7d">{t("period7days")}</option>
          <option value="30d">{t("period30days")}</option>
          <option value="90d">{t("period90days")}</option>
        </Select>
      </label>
      <label className="text-sm">
        {t("usageState")}
        <Select
          name="usage_state"
          defaultValue={usageState}
          className="border-input bg-background mt-1 w-full rounded-sm border px-2 py-1"
        >
          <option value="all">{t("usageAll")}</option>
          <option value="recorded">{t("usageRecorded")}</option>
          <option value="no_recorded">{t("usageNoRecorded")}</option>
        </Select>
      </label>
      <div className="flex items-end">
        <Button type="submit">{t("apply")}</Button>
      </div>
      <details className="sm:col-span-5">
        <summary className="cursor-pointer text-sm">{t("moreFilters")}</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <label className="text-sm">
            {t("outcome")}
            <Select
              name="outcome"
              defaultValue={selected("outcome")}
              className="border-input bg-background mt-1 w-full rounded-sm border px-2 py-1"
            >
              <option value="">{t("allOutcomes")}</option>
              <option value="succeeded">{t("outcomeSucceeded")}</option>
              <option value="failed">{t("outcomeFailed")}</option>
              <option value="cancelled">{t("outcomeCancelled")}</option>
            </Select>
          </label>
          <label className="text-sm">
            {t("collectionState")}
            <Select
              name="collection_state"
              defaultValue={selected("collection_state")}
              className="border-input bg-background mt-1 w-full rounded-sm border px-2 py-1"
            >
              <option value="">{t("collectionAll")}</option>
              <option value="complete">{t("collectionComplete")}</option>
              <option value="partial">{t("collectionPartial")}</option>
              <option value="stale">{t("collectionStale")}</option>
              <option value="unknown">{t("collectionUnknown")}</option>
              <option value="disabled">{t("collectionDisabled")}</option>
            </Select>
          </label>
          {ADDITIONAL_FILTER_FIELDS.map(({ key, labelKey }) => (
            <label key={key} className="text-sm">
              {t(labelKey)}
              <Input name={key} defaultValue={selected(key)} className="mt-1" />
            </label>
          ))}
        </div>
      </details>
      <input type="hidden" name="view" value={view} />
      <input type="hidden" name="chart" value={chart} />
      <input type="hidden" name="sort" value={sort} />
      <input type="hidden" name="order" value={order} />
      {expanded && <input type="hidden" name="expanded" value={expanded} />}
    </form>
  );
}
