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
