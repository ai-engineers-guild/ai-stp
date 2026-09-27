import { apiRequest } from "@/lib/api/http";
import { ApiError } from "@/lib/api/errors";
import type {
  CorporateContext,
  RuntimeUsageEventList,
  RuntimeUsageObjectRow,
  RuntimeUsageReport,
} from "@/lib/api/generated/types.gen";

export type UsageQueryParams = Record<string, string | string[] | undefined>;

export type UsageFilterKeys =
  | "team_id"
  | "employee_id"
  | "project_id"
  | "technology_id"
  | "harness"
  | "device_id"
  | "setup_stable_id"
  | "component_stable_id"
  | "outcome";

export const FILTER_KEYS: readonly UsageFilterKeys[] = [
  "team_id",
  "employee_id",
  "project_id",
  "technology_id",
  "harness",
  "device_id",
  "setup_stable_id",
  "component_stable_id",
  "outcome",
];

export function calculateInvokedFrom(period: string): string {
  const days = Number(period.slice(0, -1));
  const ms = (Number.isFinite(days) && days > 0 ? days : 7) * 86_400_000;
  return new Date(Date.now() - ms).toISOString();
}

export function parseUsageQuery(query: UsageQueryParams) {
  const selected = (key: string) => {
    const val = query[key];
    return typeof val === "string" && val.length <= 128 ? val : "";
  };

  const employeeId = selected("employee_id");
  const view = query.view === "objects" ? "objects" : "employees";
  const chart: "day" | "hour" = query.chart === "hour" ? "hour" : "day";
  const expanded = selected("expanded");
  const sort = [
    "item",
    "employee",
    "assigned",
    "installed",
    "used_by",
    "uses",
    "active_days",
    "last_used",
  ].includes(selected("sort"))
    ? selected("sort")
    : "uses";
  const order = selected("order") === "asc" ? "asc" : "desc";
  const requestedPage = /^\d+$/.test(selected("page")) ? Math.max(1, Number(selected("page"))) : 1;
  const period = ["7d", "30d", "90d"].includes(selected("period")) ? selected("period") : "7d";

  const paramsForApi = new URLSearchParams({
    group_by: "component",
    invoked_from: calculateInvokedFrom(period),
  });

  for (const key of FILTER_KEYS) {
    if (selected(key)) paramsForApi.set(key, selected(key));
  }

  const usageState = ["recorded", "no_recorded"].includes(selected("usage_state"))
    ? selected("usage_state")
    : "all";
  paramsForApi.set("usage_state", usageState);
  const collectionState = ["complete", "partial", "stale", "unknown", "disabled"].includes(
    selected("collection_state"),
  )
    ? selected("collection_state")
    : "all";
  paramsForApi.set("collection_state", collectionState);

  const viewQuery = new URLSearchParams();
  for (const key of [
    ...FILTER_KEYS,
    "usage_state",
    "collection_state",
    "period",
    "chart",
    "expanded",
    "sort",
    "order",
    "page",
  ] as const) {
    if (selected(key)) viewQuery.set(key, selected(key));
  }

  return {
    selected,
    employeeId,
    view,
    chart,
    expanded,
    sort,
    order,
    requestedPage,
    period,
    usageState,
    paramsForApi,
    viewQuery,
  };
}

export async function fetchUsageReportData(
  organizationId: string,
  token: string,
  paramsForApi: URLSearchParams,
): Promise<RuntimeUsageReport | null> {
  try {
    return await apiRequest<RuntimeUsageReport>(
      `/v1/corporate/organizations/${organizationId}/telemetry/usage-reports?${paramsForApi}`,
      { sessionToken: token },
    );
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return null;
  }
}

export async function fetchUsageEventsData(
  organizationId: string,
  token: string,
  invokedFrom: string,
  detailPage: number,
  selected: (key: string) => string,
): Promise<{ eventList: RuntimeUsageEventList | null; detailError: number | null }> {
  const eventParams = new URLSearchParams({
    invoked_from: invokedFrom,
    source: "native_hook",
    activity_kind: "invocation",
    offset: String(detailPage * 50),
    limit: "50",
  });
  for (const key of FILTER_KEYS) {
    if (selected(key)) eventParams.set(key, selected(key));
  }
  const itemKind = selected("detail_item");
  if (itemKind === "setup" || itemKind === "component") {
    if (itemKind === "setup") {
      eventParams.set("setup_stable_id", selected("detail_id"));
      eventParams.set("setup_version", selected("detail_version"));
    } else {
      eventParams.set("component_stable_id", selected("detail_id"));
      eventParams.set("component_version", selected("detail_version"));
      if (selected("detail_direct") === "1") {
        eventParams.delete("setup_stable_id");
        eventParams.set("direct_only", "true");
      } else if (selected("detail_setup_id")) {
        eventParams.set("setup_stable_id", selected("detail_setup_id"));
        eventParams.set("setup_version", selected("detail_setup_version"));
      }
    }
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(selected("detail_day")))
    eventParams.set("local_day", selected("detail_day"));
  if (/^[0-6]$/.test(selected("detail_weekday")))
    eventParams.set("local_weekday", selected("detail_weekday"));
  if (/^\d{1,2}$/.test(selected("detail_hour")))
    eventParams.set("local_hour", selected("detail_hour"));

  try {
    const list = await apiRequest<RuntimeUsageEventList>(
      `/v1/corporate/organizations/${organizationId}/telemetry/usage-events?${eventParams}`,
      { sessionToken: token },
    );
    return { eventList: list, detailError: null };
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return { eventList: null, detailError: error.status };
  }
}

function objectMetric(row: RuntimeUsageObjectRow, sort: string): number | string {
  if (sort === "assigned") return row.assigned_to;
  if (sort === "installed") return row.installed_for;
  if (sort === "used_by") return row.used_by;
  if (sort === "active_days") return row.active_days;
  if (sort === "last_used") return row.last_used_at ?? "";
  if (sort === "item" || sort === "employee") return row.name ?? row.stable_id;
  return row.uses;
}

export function sortObjects(
  rows: RuntimeUsageObjectRow[],
  sort: string,
  direction: number,
): RuntimeUsageObjectRow[] {
  return [...rows].sort((left, right) => {
    const a = objectMetric(left, sort);
    const b = objectMetric(right, sort);
    return (
      direction *
      (typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b)))
    );
  });
}

export function sortEmployees(
  employees: RuntimeUsageReport["employees"],
  sort: string,
  direction: number,
) {
  return [...employees].sort((left, right) => {
    const a =
      sort === "assigned"
        ? left.assigned_components
        : sort === "installed"
          ? left.installed_components
          : sort === "active_days"
            ? left.active_days
            : sort === "last_used"
              ? (left.last_used_at ?? "")
              : sort === "employee" || sort === "item"
                ? (left.name ?? left.employee_id)
                : left.uses;
    const b =
      sort === "assigned"
        ? right.assigned_components
        : sort === "installed"
          ? right.installed_components
          : sort === "active_days"
            ? right.active_days
            : sort === "last_used"
              ? (right.last_used_at ?? "")
              : sort === "employee" || sort === "item"
                ? (right.name ?? right.employee_id)
                : right.uses;
    return (
      direction *
      (typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b)))
    );
  });
}

export type DisplayRow = { kind: "item"; row: RuntimeUsageObjectRow } | { kind: "direct" };

export function buildDisplayRows(
  allItems: RuntimeUsageObjectRow[],
  allObjects: RuntimeUsageObjectRow[],
  page: number,
  employeeId: string,
  expanded: string,
): DisplayRow[] {
  const displayRows: DisplayRow[] = [];
  let directHeading = false;
  for (const item of allItems.slice((page - 1) * 10, page * 10)) {
    if (item.object_kind === "component") {
      if (!directHeading) displayRows.push({ kind: "direct" });
      directHeading = true;
      displayRows.push({ kind: "item", row: item });
    } else {
      displayRows.push({ kind: "item", row: item });
    }
    if (
      item.object_kind === "setup" &&
      (employeeId || expanded === `${item.stable_id}@${item.version}`)
    ) {
      for (const child of allObjects) {
        if (
          child.parent_setup_stable_id === item.stable_id &&
          child.parent_setup_version === item.version
        ) {
          displayRows.push({ kind: "item", row: child });
        }
      }
    }
  }
  return displayRows;
}

export function buildEmployeeOptions(
  context: CorporateContext,
  data: RuntimeUsageReport | null,
): Map<string, string> {
  return new Map([
    [context.member.account_id, context.member.display_name ?? context.member.account_id],
    ...context.teams.flatMap((team) =>
      team.members.map(
        (member) => [member.account_id, member.display_name ?? member.account_id] as const,
      ),
    ),
    ...(data?.employees.map((row) => [row.employee_id, row.name ?? row.employee_id] as const) ??
      []),
  ]);
}

export function buildUsageHrefs({
  viewQuery,
  chartQuery,
  view,
  sort,
  order,
  expanded,
  selected,
}: {
  viewQuery: URLSearchParams;
  chartQuery: URLSearchParams;
  view: string;
  sort: string;
  order: string;
  expanded: string;
  selected: (key: string) => string;
}) {
  const pageHref = (target: number) => {
    const next = new URLSearchParams(viewQuery);
    if (view === "objects") next.set("view", "objects");
    next.set("page", String(target));
    return `/corporate/reports/usage?${next}`;
  };

  const sortHref = (key: string) => {
    const next = new URLSearchParams(viewQuery);
    if (view === "objects") next.set("view", "objects");
    next.set("sort", key);
    next.set("order", sort === key && order === "desc" ? "asc" : "desc");
    next.delete("page");
    return `/corporate/reports/usage?${next}`;
  };

  const employeeHref = (accountId: string) => {
    const next = new URLSearchParams(viewQuery);
    next.set("employee_id", accountId);
    next.delete("page");
    return `/corporate/reports/usage?${next}`;
  };

  const expandHref = (row: RuntimeUsageObjectRow) => {
    const next = new URLSearchParams(chartQuery);
    next.set("view", "objects");
    const key = `${row.stable_id}@${row.version}`;
    if (expanded === key) next.delete("expanded");
    else next.set("expanded", key);
    return `/corporate/reports/usage?${next}`;
  };

  const detailBase = new URLSearchParams(chartQuery);
  detailBase.set("detail", "events");
  const detailHref = (changes: Record<string, string>) => {
    const next = new URLSearchParams(detailBase);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    return `/corporate/reports/usage?${next}`;
  };

  const objectDetailHref = (row: RuntimeUsageObjectRow) =>
    detailHref({
      detail_item: row.object_kind,
      detail_id: row.stable_id,
      detail_version: row.version,
      detail_setup_id: row.parent_setup_stable_id ?? "",
      detail_setup_version: row.parent_setup_version ?? "",
      detail_direct: row.object_kind === "component" && !row.parent_setup_stable_id ? "1" : "",
      detail_day: "",
      detail_weekday: "",
      detail_hour: "",
      detail_page: "",
    });

  const detailPageHref = (targetPage: number) => {
    const next = new URLSearchParams(chartQuery);
    for (const key of [
      "detail",
      "detail_item",
      "detail_id",
      "detail_version",
      "detail_setup_id",
      "detail_setup_version",
      "detail_direct",
      "detail_day",
      "detail_weekday",
      "detail_hour",
      "employee_id",
    ] as const) {
      if (selected(key)) next.set(key, selected(key));
    }
    next.set("detail_page", String(targetPage));
    return `/corporate/reports/usage?${next}`;
  };

  return {
    pageHref,
    sortHref,
    employeeHref,
    expandHref,
    detailHref,
    objectDetailHref,
    detailPageHref,
  };
}
