import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const { exportAudit, replace } = vi.hoisted(() => ({
  exportAudit: vi.fn(),
  replace: vi.fn(),
}));
vi.mock("@/actions/corporate", () => ({
  corporateAuditExportAction: exportAudit,
}));
// Radix Dialog's focus scope loops in jsdom; the drawer's content is what this
// suite checks, so the portal primitives are replaced with passthroughs.
vi.mock("@/components/atoms/sheet", () => ({
  Sheet: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <>{children}</> : null,
  SheetClose: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SheetContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, ...props }: React.ComponentProps<"a">) => <a {...props}>{children}</a>,
  usePathname: () => "/corporate/admin/audit",
  useRouter: () => ({ replace }),
}));
vi.mock("next-intl", () => ({
  useTranslations: () => {
    const t = (key: string, values?: Record<string, string | number>) => {
      if (values?.entity !== undefined) return `${values.entity}: ${values.operation}`;
      if (values?.count !== undefined) return `${key}:${values.count}`;
      return key;
    };
    t.has = () => false;
    return t;
  },
  useFormatter: () => ({ dateTime: () => "Localized date" }),
}));

import { auditExportCsv, CorporateAuditPanel } from "@/components/organisms/corporate-audit-panel";
import type { CorporateAuditList } from "@/lib/api/generated/types.gen";

const LABELS = {
  title: "Journal",
  export: "Export",
  exporting: "Exporting",
  exportFormat: "Format",
  exportRange: "Time range",
  currentFilters: "Current filters",
  today: "Today",
  last7Days: "Last 7 days",
  last30Days: "Last 30 days",
  allEvents: "All events",
  json: "JSON",
  csv: "CSV",
  noAudit: "No events",
  failed: "Export failed",
};

function entry(overrides: Partial<CorporateAuditList["items"][number]> = {}) {
  return {
    schema_version: 1 as const,
    audit_id: 1,
    action: "role.update",
    actor_type: "user" as const,
    actor_account_id: "account_alice",
    actor_id: "account_alice",
    created_at: "2026-09-13T10:00:00Z",
    outcome: "succeeded" as const,
    target_table: "corporate_role",
    target_id: "role_auditor",
    request_id: null,
    reason: "rotate scope",
    payload: {},
    effective_role_bindings: [],
    ...overrides,
  };
}

function audit(items: CorporateAuditList["items"], total = items.length): CorporateAuditList {
  return { schema_version: 1, items, total, next_before_created_at: null, next_before_id: null };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("renders the toolbar, count, table and numbered pager", () => {
  window.history.replaceState(null, "", "/corporate/admin/audit?page=1");
  render(
    <CorporateAuditPanel
      organizationId="organization_fixture"
      audit={audit([entry()], 142)}
      members={[{ account_id: "account_alice", display_name: "Alice" }]}
      page={1}
      pageSize={10}
      labels={LABELS}
    />,
  );
  expect(screen.getByLabelText("search")).toBeInTheDocument();
  for (const name of ["allActors", "allActions", "allTypes", "allOutcomes"])
    expect(screen.getByLabelText(name)).toBeInTheDocument();
  expect(screen.getByText("eventCount:142")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Alice" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "role.update" })).toBeInTheDocument();
  expect(screen.getByLabelText("rowsPerPage")).toHaveValue("10");
  // Numbered pagination navigates through the URL.
  const pageTwo = screen
    .getAllByRole("button", { name: "page" })
    .find((button) => button.textContent === "2");
  if (!pageTwo) throw new Error("page 2 button is missing");
  fireEvent.click(pageTwo);
  expect(replace).toHaveBeenCalledWith(expect.stringContaining("page=2"), { scroll: false });
});

it("pushes filter selects into the URL and resets the page", () => {
  window.history.replaceState(null, "", "/corporate/admin/audit?page=3&outcome=failed");
  render(
    <CorporateAuditPanel
      organizationId="organization_fixture"
      audit={audit([entry({ outcome: "failed" })], 1)}
      filters={{ outcome: "failed" }}
      page={3}
      pageSize={10}
      labels={LABELS}
    />,
  );
  fireEvent.change(screen.getByLabelText("allActions"), { target: { value: "role.update" } });
  expect(replace).toHaveBeenLastCalledWith(expect.stringContaining("action=role.update"), {
    scroll: false,
  });
  expect(replace.mock.calls.at(-1)?.[0]).not.toContain("page=");
  fireEvent.click(screen.getByRole("button", { name: "reset" }));
  expect(replace).toHaveBeenLastCalledWith("/corporate/admin/audit", { scroll: false });
});

it("opens the detail drawer with request id, target and payload", () => {
  window.history.replaceState(null, "", "/corporate/admin/audit");
  render(
    <CorporateAuditPanel
      organizationId="organization_fixture"
      members={[{ account_id: "account_alice", display_name: "Alice", contact_email: "a@x.io" }]}
      audit={audit([
        entry({
          request_id: "secret_request",
          payload: { internal: "hidden_payload" },
        }),
      ])}
      labels={LABELS}
    />,
  );
  expect(screen.queryByText(/secret_request/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Alice a@x.io" }));
  expect(screen.getByRole("heading", { name: "eventDetails" })).toBeInTheDocument();
  expect(screen.getByText("secret_request")).toBeInTheDocument();
  expect(screen.getByText(/hidden_payload/)).toBeInTheDocument();
  // The reason appears once in the row and once inside the opened drawer.
  expect(screen.getAllByText(/rotate scope/)).toHaveLength(2);
});

it("shows export transport errors and permits retry without losing the journal", async () => {
  window.history.replaceState(null, "", "/corporate/admin/audit");
  exportAudit.mockRejectedValueOnce(new Error("Connection lost"));
  exportAudit.mockResolvedValueOnce({ ok: false, message: "Try again later" });
  render(
    <CorporateAuditPanel organizationId="organization_fixture" audit={audit([])} labels={LABELS} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Export" }));
  await screen.findByText("Export failed");
  expect(screen.getByText("No events")).toBeInTheDocument();
  await screen.findByRole("button", { name: "Export" });
  fireEvent.click(screen.getByRole("button", { name: "Export" }));
  await screen.findByText("Try again later");
  expect(exportAudit).toHaveBeenCalledTimes(2);
});

it("does not offer export when the server projection withholds the capability", () => {
  window.history.replaceState(null, "", "/corporate/admin/audit");
  render(
    <CorporateAuditPanel
      organizationId="organization_fixture"
      canExport={false}
      audit={audit([])}
      labels={LABELS}
    />,
  );
  expect(screen.queryByRole("button", { name: "Export" })).not.toBeInTheDocument();
});

it("creates a quoted CSV without exposing extra audit fields in the UI", () => {
  const csv = auditExportCsv({
    schema_version: 1,
    organization_id: "organization_fixture",
    exported_at: "2026-09-13T10:00:00Z",
    items: [
      entry({
        action: "member.profile.update",
        target_table: "member",
        target_id: "account_alice",
        request_id: "request-1",
        reason: 'name contains "quotes"',
        payload: { name: "Alice" },
      }),
    ],
  });
  expect(csv).toContain('"name contains ""quotes"""');
  expect(csv).toContain('"{""name"":""Alice""}"');
});

it("exports the selected range and keeps the object URL alive through the click", async () => {
  window.history.replaceState(null, "", "/corporate/admin/audit");
  exportAudit.mockResolvedValue({
    ok: true,
    data: {
      schema_version: 1,
      organization_id: "organization_fixture",
      exported_at: "2026-09-13T10:00:00Z",
      items: [],
    },
  });
  const createObjectURLMock = vi.fn(() => "blob:audit");
  const revokeObjectURLMock = vi.fn();
  URL.createObjectURL = createObjectURLMock;
  URL.revokeObjectURL = revokeObjectURLMock;
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  render(
    <CorporateAuditPanel
      organizationId="organization_fixture"
      audit={audit([])}
      filters={{ action: "member.update" }}
      labels={LABELS}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Export" }));
  const exportAuditMock = vi.mocked(exportAudit);
  await waitFor(() => {
    expect(exportAuditMock).toHaveBeenCalledWith("organization_fixture", {
      action: "member.update",
    });
  });
  expect(createObjectURLMock).toHaveBeenCalledOnce();
  await waitFor(() => {
    expect(revokeObjectURLMock).toHaveBeenCalledWith("blob:audit");
  });
});
