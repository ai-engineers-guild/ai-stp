import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const { exportAudit } = vi.hoisted(() => ({ exportAudit: vi.fn() }));
vi.mock("@/actions/corporate", () => ({
  corporateAuditExportAction: exportAudit,
}));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, ...props }: React.ComponentProps<"a">) => <a {...props}>{children}</a>,
}));
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) =>
    values ? `${values.entity}: ${values.operation}` : key,
  useFormatter: () => ({ dateTime: () => "Localized date" }),
}));
import { auditExportCsv, CorporateAuditPanel } from "@/components/organisms/corporate-audit-panel";
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
it("links named actors and hides technical fields even for unknown events", () => {
  render(
    <CorporateAuditPanel
      organizationId="organization_fixture"
      members={[{ account_id: "account_alice", display_name: "Alice" }]}
      audit={{
        schema_version: 1,
        next_before_created_at: null,
        next_before_id: null,
        items: [
          {
            schema_version: 1,
            audit_id: 1,
            action: "unknown.internal.operation",
            actor_type: "user",
            actor_account_id: "account_alice",
            actor_id: "account_alice",
            created_at: "2026-09-13T10:00:00Z",
            outcome: "succeeded",
            target_table: "internal_table",
            target_id: "internal_target",
            request_id: "secret_request",
            reason: null,
            payload: { internal: "hidden_payload" },
            effective_role_bindings: [],
          },
        ],
      }}
      labels={{
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
      }}
    />,
  );
  expect(screen.getByRole("link", { name: "Alice" })).toHaveAttribute(
    "href",
    "/corporate/employees/account_alice",
  );
  expect(screen.getByText("otherEvent")).toBeInTheDocument();
  expect(screen.getByText("Localized date")).toHaveAttribute("dateTime", "2026-09-13T10:00:00Z");
  for (const value of [
    "unknown.internal.operation",
    "internal_table",
    "internal_target",
    "secret_request",
    "hidden_payload",
  ])
    expect(screen.queryByText(new RegExp(value))).not.toBeInTheDocument();
});
it("shows export transport errors and permits retry without losing the journal", async () => {
  exportAudit.mockRejectedValueOnce(new Error("Connection lost"));
  exportAudit.mockResolvedValueOnce({ ok: false, message: "Try again later" });
  render(
    <CorporateAuditPanel
      organizationId="organization_fixture"
      audit={{
        schema_version: 1,
        items: [],
        next_before_created_at: null,
        next_before_id: null,
      }}
      labels={{
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
      }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Export" }));
  await screen.findByText("Export failed");
  expect(screen.getByText("No events")).toBeInTheDocument();
  await screen.findByRole("button", { name: "Export" });
  expect(screen.getByRole("button", { name: "Export" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Export" }));
  await screen.findByText("Try again later");
  expect(exportAudit).toHaveBeenCalledTimes(2);
});
it("creates a quoted CSV without exposing extra audit fields in the UI", () => {
  const csv = auditExportCsv({
    schema_version: 1,
    organization_id: "organization_fixture",
    exported_at: "2026-09-13T10:00:00Z",
    items: [
      {
        schema_version: 1,
        audit_id: 1,
        action: "member.profile.update",
        actor_type: "user",
        actor_account_id: "account_alice",
        actor_id: "account_alice",
        created_at: "2026-09-13T10:00:00Z",
        outcome: "succeeded",
        target_table: "member",
        target_id: "account_alice",
        request_id: "request-1",
        reason: 'name contains "quotes"',
        payload: { name: "Alice" },
        effective_role_bindings: [],
      },
    ],
  });
  expect(csv).toContain('"name contains ""quotes"""');
  expect(csv).toContain('"{""name"":""Alice""}"');
});
