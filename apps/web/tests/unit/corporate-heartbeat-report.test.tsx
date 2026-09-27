import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  CorporateHeartbeatReport,
  type HeartbeatReportData,
} from "@/components/organisms/corporate-heartbeat-report";

const push = vi.hoisted(() => vi.fn());
const replace = vi.hoisted(() => vi.fn());
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ push, replace }),
  usePathname: () => "/corporate/reports/heartbeat",
  Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

const report = {
  evaluated_at: "2026-09-25T12:00:00Z",
  interval_seconds: 900,
  stale_after_seconds: 3600,
  total: 0,
  page: 1,
  page_size: 10,
  teams: [],
  employees: [],
  items: [],
} as unknown as HeartbeatReportData;

afterEach(() => {
  cleanup();
  push.mockClear();
  replace.mockClear();
});

it("checks filters immediately and combines quick selections into one navigation", async () => {
  window.history.replaceState(null, "", "/corporate/reports/heartbeat");
  render(
    <CorporateHeartbeatReport
      report={{
        ...report,
        teams: [
          { id: "team-1", name: "Engineering" },
          { id: "team-2", name: "Product" },
        ],
      }}
      view="current"
      period="7d"
      fromDate=""
      toDate=""
      selectedTeams={[]}
      selectedEmployees={[]}
      selectedStatuses={[]}
      sort="last_heartbeat"
      order="desc"
      locale="en"
    />,
  );
  fireEvent.click(screen.getByText("allTeams"));
  fireEvent.click(screen.getByRole("checkbox", { name: "Engineering" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Product" }));
  expect(screen.getByRole("checkbox", { name: "Engineering" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Product" })).toBeChecked();
  expect(replace).not.toHaveBeenCalled();
  await waitFor(() => {
    expect(replace).toHaveBeenCalledWith("/corporate/reports/heartbeat?team=team-1&team=team-2", {
      scroll: false,
    });
  });
  expect(replace).toHaveBeenCalledTimes(1);
});

it("shows the in-table empty state and sorts through the URL", () => {
  window.history.replaceState(null, "", "/corporate/reports/heartbeat?view=current");
  render(
    <CorporateHeartbeatReport
      report={report}
      view="current"
      period="7d"
      fromDate=""
      toDate=""
      selectedTeams={[]}
      selectedEmployees={[]}
      selectedStatuses={[]}
      sort="last_heartbeat"
      order="desc"
      locale="en"
    />,
  );
  expect(screen.getByText("empty")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "employee" }));
  expect(push).toHaveBeenCalledWith(
    "/corporate/reports/heartbeat?view=current&sort=employee&order=asc",
  );
});

const item = (
  accountId: string,
  employee: string,
  deviceId: string,
  deviceName: string,
  status: string,
) =>
  ({
    account_id: accountId,
    employee_name: employee,
    teams: [{ id: "team-1", name: "Data Platform" }],
    device_id: deviceId,
    device_name: deviceName,
    last_heartbeat_at: "2026-09-25T11:00:00Z",
    status,
    buckets: [],
    coverage_percent: null,
  }) as HeartbeatReportData["items"][number];

it("groups devices under the employee and reveals them on expand", () => {
  window.history.replaceState(null, "", "/corporate/reports/heartbeat?view=current");
  render(
    <CorporateHeartbeatReport
      report={{
        ...report,
        total: 3,
        items: [
          item("acc-a", "Artem Letyushev", "dev-1", "DESKTOP-A", "active"),
          item("acc-a", "Artem Letyushev", "dev-2", "DESKTOP-B", "unknown"),
          item("acc-b", "Mikhail Orlov", "dev-3", "DESKTOP-C", "unknown"),
        ],
      }}
      view="current"
      period="7d"
      fromDate=""
      toDate=""
      selectedTeams={[]}
      selectedEmployees={[]}
      selectedStatuses={[]}
      sort="last_heartbeat"
      order="desc"
      locale="en"
    />,
  );
  // One row per employee: the multi-device person collapses to a single line.
  expect(screen.getAllByText("Artem Letyushev")).toHaveLength(1);
  expect(screen.queryByText("DESKTOP-A")).not.toBeInTheDocument();
  // Single-device employees still show the device inline.
  expect(screen.getByText("DESKTOP-C")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "expandDevices" }));
  expect(screen.getByText("DESKTOP-A")).toBeInTheDocument();
  expect(screen.getByText("DESKTOP-B")).toBeInTheDocument();
});

it("keeps the selected view when moving to the next page", () => {
  window.history.replaceState(null, "", "/corporate/reports/heartbeat?view=history&period=7d");
  render(
    <CorporateHeartbeatReport
      report={{ ...report, total: 11 }}
      view="history"
      period="7d"
      fromDate=""
      toDate=""
      selectedTeams={[]}
      selectedEmployees={[]}
      selectedStatuses={[]}
      sort="last_heartbeat"
      order="desc"
      locale="en"
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "next" }));
  expect(push).toHaveBeenCalledWith("/corporate/reports/heartbeat?view=history&period=7d&page=2");
});
