"use client";
/* eslint-disable max-lines, max-lines-per-function -- one bounded constructor and its accessible result views share the query state. */

import { useEffect, useState, useTransition } from "react";
import { useTranslations } from "next-intl";

import {
  listDashboardViewsAction,
  queryDashboardAction,
  saveDashboardViewAction,
} from "@/actions/dashboard";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { StatePanel } from "@/components/molecules/state-panel";
import type { DashboardQuery, DashboardResult, DashboardView } from "@/lib/api/generated/types.gen";

type Dimension = NonNullable<DashboardQuery["dimensions"]>[number];
type Measure = NonNullable<DashboardQuery["measures"]>[number];
type Chart = NonNullable<DashboardQuery["view"]>;
type Scope = DashboardView["scope"];
type Props = {
  csrfToken: string;
  accountId: string;
  organizationId: string;
  teams: { id: string; name: string }[];
  canShareOrganization: boolean;
  canReadDiagnostics: boolean;
};

const dimensions: Dimension[] = [
  "state",
  "project",
  "team",
  "account",
  "device",
  "harness",
  "setup",
  "provider",
  "day",
  "checked_at",
  "reason",
];
const measures: Measure[] = ["count", "devices", "projects"];
const charts: Chart[] = ["table", "bar", "line", "pie", "heatmap"];
const allowedDimensions: Record<DashboardQuery["dataset"], Dimension[]> = {
  ci: dimensions,
  heartbeat: ["state", "team", "account", "device", "day", "checked_at"],
  provider: ["state", "team", "account", "device", "harness", "provider", "day", "checked_at"],
};
const initialQuery: DashboardQuery = {
  dataset: "ci",
  dimensions: ["state"],
  measures: ["count"],
  filters: [],
  group_by: [],
  pivot_rows: [],
  pivot_columns: [],
  sort_by: "count",
  sort_order: "desc",
  view: "bar",
  limit: 100,
};

function selectedDimensions(query: DashboardQuery): Dimension[] {
  return [
    ...new Set([
      ...(query.dimensions ?? []),
      ...(query.group_by ?? []),
      ...(query.pivot_rows ?? []),
      ...(query.pivot_columns ?? []),
    ]),
  ];
}

function dimensionLabel(item: DashboardResult["items"][number], keys: Dimension[]) {
  return keys.map((key) => item.dimensions[key] ?? "—").join(" · ") || "—";
}

// The existing kit has controls and state panels; no chart organism accepts this bounded aggregate contract.
export function DashboardBuilder({
  csrfToken,
  accountId,
  organizationId,
  teams,
  canShareOrganization,
  canReadDiagnostics,
}: Props) {
  const t = useTranslations("dashboardBuilder");
  const [query, setQuery] = useState<DashboardQuery>(initialQuery);
  const [result, setResult] = useState<DashboardResult | null>(null);
  const [saved, setSaved] = useState<DashboardView[]>([]);
  const [selectedView, setSelectedView] = useState("");
  const [name, setName] = useState("");
  const [scope, setScope] = useState<Scope>("user");
  const [teamId, setTeamId] = useState(teams[0]?.id ?? "");
  const [filterDimension, setFilterDimension] = useState<Dimension>("state");
  const [filterValues, setFilterValues] = useState("");
  const [error, setError] = useState("");
  const [loading, startTransition] = useTransition();

  useEffect(() => {
    let active = true;
    void listDashboardViewsAction({ csrfToken }).then((response) => {
      if (active && response.ok) setSaved(response.data.items);
    });
    return () => {
      active = false;
    };
  }, [csrfToken]);

  function run(next: DashboardQuery = query) {
    setError("");
    startTransition(async () => {
      const response = await queryDashboardAction({ csrfToken, query: next });
      if (response.ok) setResult(response.data);
      else {
        setResult(null);
        setError(response.message);
      }
    });
  }

  function save() {
    if (!name.trim()) {
      setError(t("nameRequired"));
      return;
    }
    const current = saved.find((item) => item.id === selectedView);
    setError("");
    startTransition(async () => {
      const response = await saveDashboardViewAction({
        csrfToken,
        name: name.trim(),
        scope,
        scopeId: scope === "user" ? accountId : scope === "team" ? teamId : organizationId,
        query,
        ...(current ? { viewId: current.id, expectedRevision: current.revision } : {}),
        idempotencyKey: crypto.randomUUID(),
      });
      if (!response.ok) {
        setError(response.message);
        return;
      }
      setSaved((items) => [response.data, ...items.filter((item) => item.id !== response.data.id)]);
      setSelectedView(response.data.id);
    });
  }

  function load(id: string) {
    setSelectedView(id);
    const item = saved.find((entry) => entry.id === id);
    if (!item) return;
    setName(item.name);
    setScope(item.scope);
    if (item.scope === "team") setTeamId(item.scope_id);
    setQuery(item.query);
    run(item.query);
  }

  function setDataset(dataset: DashboardQuery["dataset"]) {
    setQuery({ ...initialQuery, dataset });
    setResult(null);
    setFilterDimension("state");
  }

  const available = allowedDimensions[query.dataset].filter(
    (value) => value !== "reason" || canReadDiagnostics,
  );
  const selected = selectedDimensions(query);
  const chosenMeasure = query.measures?.[0] ?? "count";
  const selectClass =
    "border-input bg-background text-foreground focus-visible:ring-ring min-h-10 w-full rounded-sm border px-3 text-sm focus-visible:outline-none focus-visible:ring-2";
  return (
    <div className="space-y-6">
      <section
        className="border-border bg-card rounded-lg border p-4 sm:p-6"
        aria-label={t("constructor")}
      >
        <h2 className="text-lg font-medium">{t("constructor")}</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="space-y-1 text-sm">
            <span>{t("dataset")}</span>
            <select
              className={selectClass}
              value={query.dataset}
              onChange={(e) => {
                setDataset(e.target.value as DashboardQuery["dataset"]);
              }}
            >
              {(["ci", "heartbeat", "provider"] as const).map((value) => (
                <option key={value} value={value}>
                  {t(`datasetNames.${value}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("view")}</span>
            <select
              className={selectClass}
              value={query.view}
              onChange={(e) => {
                setQuery({
                  ...query,
                  view: e.target.value as Chart,
                  dimensions:
                    e.target.value === "line"
                      ? ["day"]
                      : e.target.value === "pie"
                        ? ["state"]
                        : e.target.value === "heatmap"
                          ? ["state", "account"]
                          : (query.dimensions ?? []),
                  sort_by:
                    e.target.value === "line"
                      ? "day"
                      : e.target.value === "pie" || e.target.value === "heatmap"
                        ? "count"
                        : (query.sort_by ?? "count"),
                  sort_order: e.target.value === "line" ? "asc" : (query.sort_order ?? "desc"),
                  ...(e.target.value === "pie" || e.target.value === "heatmap"
                    ? { group_by: [], pivot_rows: [], pivot_columns: [] }
                    : {}),
                });
              }}
            >
              {charts.map((value) => (
                <option key={value} value={value}>
                  {t(`charts.${value}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("sort")}</span>
            <select
              className={selectClass}
              value={query.sort_by}
              onChange={(e) => {
                setQuery({
                  ...query,
                  sort_by: e.target.value as NonNullable<DashboardQuery["sort_by"]>,
                });
              }}
            >
              {[...(query.measures ?? []), ...selected].map((value) => (
                <option key={value} value={value}>
                  {t(`fields.${value}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("sortOrder")}</span>
            <select
              className={selectClass}
              value={query.sort_order}
              onChange={(e) => {
                setQuery({
                  ...query,
                  sort_order: e.target.value as NonNullable<DashboardQuery["sort_order"]>,
                });
              }}
            >
              <option value="desc">{t("descending")}</option>
              <option value="asc">{t("ascending")}</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("limit")}</span>
            <Input
              type="number"
              min={1}
              max={200}
              value={query.limit}
              onChange={(e) => {
                setQuery({ ...query, limit: Number(e.target.value) });
              }}
            />
          </label>
        </div>
        <fieldset className="mt-5">
          <legend className="text-sm font-medium">{t("dimensions")}</legend>
          <div className="mt-2 flex flex-wrap gap-3">
            {available.map((value) => (
              <label key={value} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="accent-primary size-4"
                  checked={query.dimensions?.includes(value) ?? false}
                  disabled={
                    !(query.dimensions?.includes(value) ?? false) &&
                    (query.dimensions?.length ?? 0) >= 8
                  }
                  onChange={(e) => {
                    setQuery({
                      ...query,
                      dimensions: e.target.checked
                        ? [...(query.dimensions ?? []), value]
                        : (query.dimensions ?? []).filter((item) => item !== value),
                      sort_by:
                        !e.target.checked && query.sort_by === value
                          ? (query.measures?.[0] ?? "count")
                          : (query.sort_by ?? "count"),
                    });
                  }}
                />
                {t(`fields.${value}`)}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="mt-5">
          <legend className="text-sm font-medium">{t("measures")}</legend>
          <div className="mt-2 flex flex-wrap gap-3">
            {measures
              .filter((value) => value !== "projects" || query.dataset === "ci")
              .map((value) => (
                <label key={value} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="accent-primary size-4"
                    checked={query.measures?.includes(value) ?? false}
                    disabled={
                      (query.measures?.length ?? 0) === 1 && query.measures?.includes(value)
                    }
                    onChange={(e) => {
                      const selectedMeasures = e.target.checked
                        ? [...(query.measures ?? []), value]
                        : (query.measures ?? []).filter((item) => item !== value);
                      setQuery({
                        ...query,
                        measures: selectedMeasures,
                        sort_by:
                          !e.target.checked && query.sort_by === value
                            ? (selectedMeasures[0] ?? "count")
                            : (query.sort_by ?? "count"),
                      });
                    }}
                  />
                  {t(`fields.${value}`)}
                </label>
              ))}
          </div>
        </fieldset>
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          {(["group_by", "pivot_rows", "pivot_columns"] as const).map((field) => (
            <label key={field} className="space-y-1 text-sm">
              <span>{t(field)}</span>
              <select
                className={selectClass}
                value={query[field]?.[0] ?? ""}
                onChange={(e) => {
                  setQuery({
                    ...query,
                    [field]: e.target.value ? [e.target.value as Dimension] : [],
                  });
                }}
              >
                <option value="">{t("none")}</option>
                {available.map((value) => (
                  <option key={value} value={value}>
                    {t(`fields.${value}`)}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_2fr_auto] sm:items-end">
          <label className="space-y-1 text-sm">
            <span>{t("filterDimension")}</span>
            <select
              className={selectClass}
              value={filterDimension}
              onChange={(e) => {
                setFilterDimension(e.target.value as Dimension);
              }}
            >
              {available.map((value) => (
                <option key={value} value={value}>
                  {t(`fields.${value}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("filterValues")}</span>
            <Input
              value={filterValues}
              onChange={(e) => {
                setFilterValues(e.target.value);
              }}
              placeholder={t("filterPlaceholder")}
            />
          </label>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              const values = filterValues
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean);
              if (values.length)
                setQuery({
                  ...query,
                  filters: [
                    ...(query.filters ?? []).filter((item) => item.dimension !== filterDimension),
                    { dimension: filterDimension, values },
                  ],
                });
              setFilterValues("");
            }}
          >
            {t("addFilter")}
          </Button>
        </div>
        {(query.filters?.length ?? 0) > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {query.filters?.map((filter) => (
              <Button
                key={filter.dimension}
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  setQuery({
                    ...query,
                    filters: (query.filters ?? []).filter(
                      (item) => item.dimension !== filter.dimension,
                    ),
                  });
                }}
              >
                {t(`fields.${filter.dimension}`)}: {filter.values.join(", ")} ×
              </Button>
            ))}
          </div>
        )}
        <div className="mt-5 flex flex-wrap gap-3">
          <Button
            type="button"
            disabled={loading}
            onClick={() => {
              run();
            }}
          >
            {loading ? t("loading") : t("run")}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setQuery({
                dataset: "ci",
                view: "table",
                dimensions: [
                  "state",
                  "project",
                  "account",
                  "device",
                  "harness",
                  "setup",
                  "checked_at",
                  ...(canReadDiagnostics ? ["reason" as const] : []),
                ],
                measures: ["count"],
                sort_by: "checked_at",
                sort_order: "desc",
                filters: [],
                group_by: [],
                pivot_rows: [],
                pivot_columns: [],
                limit: 200,
              });
              setResult(null);
            }}
          >
            {t("ciDetails")}
          </Button>
        </div>
      </section>

      <section
        className="border-border bg-card rounded-lg border p-4 sm:p-6"
        aria-label={t("savedViews")}
      >
        <h2 className="text-lg font-medium">{t("savedViews")}</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="space-y-1 text-sm">
            <span>{t("loadView")}</span>
            <select
              className={selectClass}
              value={selectedView}
              onChange={(e) => {
                load(e.target.value);
              }}
            >
              <option value="">{t("newView")}</option>
              {saved.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("name")}</span>
            <Input
              value={name}
              maxLength={120}
              onChange={(e) => {
                setName(e.target.value);
              }}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t("scope")}</span>
            <select
              className={selectClass}
              value={scope}
              disabled={Boolean(selectedView)}
              onChange={(e) => {
                setScope(e.target.value as Scope);
              }}
            >
              <option value="user">{t("scopes.user")}</option>
              {teams.length > 0 && <option value="team">{t("scopes.team")}</option>}
              {canShareOrganization && (
                <option value="organization">{t("scopes.organization")}</option>
              )}
            </select>
          </label>
          {scope === "team" && (
            <label className="space-y-1 text-sm">
              <span>{t("team")}</span>
              <select
                className={selectClass}
                value={teamId}
                disabled={Boolean(selectedView)}
                onChange={(e) => {
                  setTeamId(e.target.value);
                }}
              >
                {teams.map((team) => (
                  <option key={team.id} value={team.id}>
                    {team.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <div className="mt-4">
          <Button
            type="button"
            variant="outline"
            disabled={loading || (scope === "team" && !teamId)}
            onClick={save}
          >
            {t("save")}
          </Button>
        </div>
      </section>

      {error && <StatePanel kind="error" title={t("requestFailed")} description={error} />}
      {result && (
        <DashboardVisual result={result} measure={result.query.measures?.[0] ?? chosenMeasure} />
      )}
    </div>
  );
}

function DashboardVisual({ result, measure }: { result: DashboardResult; measure: Measure }) {
  const t = useTranslations("dashboardBuilder");
  const dimensions = selectedDimensions(result.query);
  const items = result.items;
  const max = Math.max(1, ...items.map((item) => item.measures[measure] ?? 0));
  const total = items.reduce((sum, item) => sum + (item.measures[measure] ?? 0), 0);
  const chartItems = items.slice(0, 20);
  const piePalette = [
    "stroke-primary",
    "stroke-success",
    "stroke-warning",
    "stroke-destructive",
    "stroke-muted-foreground",
  ];
  return (
    <section
      className="border-border bg-card rounded-lg border p-4 sm:p-6"
      aria-label={t("results")}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-medium">{t("results")}</h2>
        <p className="text-muted-foreground text-sm">
          {t("summary", { rows: result.total_source_rows, groups: result.total_groups })}
        </p>
      </div>
      {items.length === 0 ? (
        <StatePanel
          kind="empty"
          title={t("empty")}
          description={t("emptyDescription")}
          className="mt-4"
        />
      ) : (
        <>
          {result.query.view === "bar" && (
            <div className="mt-5 space-y-3" role="img" aria-label={t("charts.bar")}>
              {chartItems.map((item, index) => (
                <div
                  key={index}
                  className="grid grid-cols-[minmax(7rem,1fr)_3fr_auto] items-center gap-3 text-sm"
                >
                  <span className="min-w-0 truncate" title={dimensionLabel(item, dimensions)}>
                    {dimensionLabel(item, dimensions)}
                  </span>
                  <div className="bg-muted h-5 rounded-sm">
                    <div
                      className="bg-primary h-5 rounded-sm"
                      style={{ width: `${(100 * (item.measures[measure] ?? 0)) / max}%` }}
                    />
                  </div>
                  <span className="font-mono">{item.measures[measure] ?? 0}</span>
                </div>
              ))}
            </div>
          )}
          {result.query.view === "line" && (
            <div className="mt-5 overflow-x-auto">
              <svg
                role="img"
                aria-label={t("charts.line")}
                viewBox="0 0 600 180"
                className="text-primary h-44 w-full min-w-[320px]"
              >
                <polyline
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="3"
                  points={chartItems
                    .map(
                      (item, index) =>
                        `${chartItems.length === 1 ? 300 : 10 + (index * 580) / (chartItems.length - 1)},${170 - (150 * (item.measures[measure] ?? 0)) / max}`,
                    )
                    .join(" ")}
                />
                {chartItems.map((item, index) => (
                  <circle
                    key={index}
                    cx={
                      chartItems.length === 1 ? 300 : 10 + (index * 580) / (chartItems.length - 1)
                    }
                    cy={170 - (150 * (item.measures[measure] ?? 0)) / max}
                    r="4"
                    fill="currentColor"
                  >
                    <title>
                      {dimensionLabel(item, dimensions)}: {item.measures[measure] ?? 0}
                    </title>
                  </circle>
                ))}
              </svg>
            </div>
          )}
          {result.query.view === "pie" && (
            <div className="mt-5 flex flex-wrap items-center gap-6">
              <svg
                role="img"
                aria-label={t("charts.pie")}
                viewBox="0 0 120 120"
                className="size-40 shrink-0 -rotate-90"
              >
                {items.map((item, index) => {
                  const share = total ? (item.measures[measure] ?? 0) / total : 0;
                  const circle = (
                    <circle
                      key={index}
                      cx="60"
                      cy="60"
                      r="48"
                      fill="none"
                      className={piePalette[index % piePalette.length]}
                      strokeWidth="20"
                      strokeDasharray={`${share * 301.59} 301.59`}
                      strokeDashoffset={
                        (-items
                          .slice(0, index)
                          .reduce((sum, previous) => sum + (previous.measures[measure] ?? 0), 0) *
                          301.59) /
                        (total || 1)
                      }
                    >
                      <title>
                        {dimensionLabel(item, dimensions)}: {item.measures[measure] ?? 0}
                      </title>
                    </circle>
                  );
                  return circle;
                })}
              </svg>
              <ul className="space-y-1 text-sm">
                {items.map((item, index) => (
                  <li key={index}>
                    {dimensionLabel(item, dimensions)}: {item.measures[measure] ?? 0}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {result.query.view === "heatmap" && (
            <div
              className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6"
              role="img"
              aria-label={t("charts.heatmap")}
            >
              {chartItems.map((item, index) => (
                <div
                  key={index}
                  className="border-border relative min-h-20 overflow-hidden rounded-sm border p-2 text-xs"
                >
                  <div
                    className="bg-primary absolute inset-0"
                    style={{ opacity: 0.1 + (0.8 * (item.measures[measure] ?? 0)) / max }}
                  />
                  <div className="relative">
                    <span className="break-all">{dimensionLabel(item, dimensions)}</span>
                    <strong className="mt-2 block font-mono">{item.measures[measure] ?? 0}</strong>
                  </div>
                </div>
              ))}
            </div>
          )}
          {(result.query.pivot_rows?.length ?? 0) > 0 &&
            (result.query.pivot_columns?.length ?? 0) > 0 && (
              <PivotTable result={result} measure={measure} />
            )}
          <div className="mt-5 max-w-full overflow-x-auto">
            <table className="w-full min-w-max border-collapse text-left text-sm">
              <caption className="sr-only">{t("results")}</caption>
              <thead>
                <tr className="border-border border-b">
                  {dimensions.map((key) => (
                    <th key={key} scope="col" className="p-2 font-medium">
                      {t(`fields.${key}`)}
                    </th>
                  ))}
                  {(result.query.measures ?? []).map((key) => (
                    <th key={key} scope="col" className="p-2 font-medium">
                      {t(`fields.${key}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((item, index) => (
                  <tr key={index} className="border-border border-b">
                    {dimensions.map((key) => (
                      <td key={key} className="p-2">
                        {item.dimensions[key] ?? "—"}
                      </td>
                    ))}
                    {(result.query.measures ?? []).map((key) => (
                      <td key={key} className="p-2 font-mono">
                        {item.measures[key] ?? 0}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function PivotTable({ result, measure }: { result: DashboardResult; measure: Measure }) {
  const t = useTranslations("dashboardBuilder");
  const rowKey = result.query.pivot_rows?.[0];
  const columnKey = result.query.pivot_columns?.[0];
  if (!rowKey || !columnKey) return null;
  const rows = [...new Set(result.items.map((item) => item.dimensions[rowKey] ?? "—"))].sort();
  const columns = [
    ...new Set(result.items.map((item) => item.dimensions[columnKey] ?? "—")),
  ].sort();
  const cells = new Map<string, number>();
  for (const item of result.items) {
    const key = `${item.dimensions[rowKey] ?? "—"}\u0000${item.dimensions[columnKey] ?? "—"}`;
    cells.set(key, (cells.get(key) ?? 0) + (item.measures[measure] ?? 0));
  }
  return (
    <div className="mt-5 max-w-full overflow-x-auto">
      <table className="w-full min-w-max border-collapse text-left text-sm">
        <caption className="mb-2 text-left font-medium">{t("pivotTitle")}</caption>
        <thead>
          <tr className="border-border border-b">
            <th scope="col" className="p-2">
              {t(`fields.${rowKey}`)} / {t(`fields.${columnKey}`)}
            </th>
            {columns.map((column) => (
              <th key={column} scope="col" className="p-2">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row} className="border-border border-b">
              <th scope="row" className="p-2 font-medium">
                {row}
              </th>
              {columns.map((column) => (
                <td key={column} className="p-2 font-mono">
                  {cells.get(`${row}\u0000${column}`) ?? 0}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
