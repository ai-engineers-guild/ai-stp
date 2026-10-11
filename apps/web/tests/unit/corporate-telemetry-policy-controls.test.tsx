import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const save = vi.hoisted(() => vi.fn());
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: { count?: number }) =>
    values?.count !== undefined ? `${key}:${values.count}` : key,
}));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, ...props }: React.ComponentProps<"a">) => <a {...props}>{children}</a>,
}));
vi.mock("@/components/organisms/corporate-governance-controls", () => ({
  useGovernanceMutation: () => ({ busy: false, message: null, save }),
}));

import { CorporateTelemetryPolicyControls } from "@/components/organisms/corporate-telemetry-policy-controls";

beforeEach(() => save.mockClear());

function renderForm(tab: "heartbeat" | "usage" | "retention" = "heartbeat") {
  render(
    <CorporateTelemetryPolicyControls
      policy={null}
      tab={tab}
      organizationId="organization_test"
      authorizationRevision={7}
      csrfToken="csrf"
    />,
  );
}

function submit() {
  const form = screen.getByRole("button", { name: "saveChanges" }).closest("form");
  if (!form) throw new Error("telemetry policy form is missing");
  fireEvent.submit(form);
}

it("submits a preset heartbeat interval in seconds", () => {
  renderForm();
  fireEvent.change(screen.getByLabelText("heartbeatInterval"), { target: { value: "60" } });
  submit();
  expect(save).toHaveBeenCalledWith(
    "/v1/corporate/organizations/organization_test/telemetry/policy",
    expect.objectContaining({ heartbeat_interval_seconds: 60, expected_policy_revision: 0 }),
    "PUT",
    expect.any(Function),
  );
});

it("maps a custom minute interval back to seconds", () => {
  renderForm();
  fireEvent.change(screen.getByLabelText("heartbeatInterval"), { target: { value: "custom" } });
  fireEvent.change(screen.getByLabelText("customIntervalMinutes"), { target: { value: "15" } });
  submit();
  expect(save).toHaveBeenCalledWith(
    expect.any(String),
    expect.objectContaining({ heartbeat_interval_seconds: 900 }),
    "PUT",
    expect.any(Function),
  );
});

it("submits the heartbeat switch as a boolean string", () => {
  renderForm();
  // The heartbeat switch starts enabled (policy fallback); uncheck it.
  fireEvent.click(screen.getByRole("checkbox", { name: "heartbeatCardTitle" }));
  submit();
  expect(save).toHaveBeenCalledWith(
    expect.any(String),
    expect.objectContaining({ heartbeat_enabled: false }),
    "PUT",
    expect.any(Function),
  );
});

it("maps the advanced retry max from minutes to seconds", () => {
  renderForm();
  fireEvent.change(screen.getByLabelText("heartbeatRetryMaxMinutes"), {
    target: { value: "120" },
  });
  submit();
  expect(save).toHaveBeenCalledWith(
    expect.any(String),
    expect.objectContaining({ heartbeat_retry_max_seconds: 7200 }),
    "PUT",
    expect.any(Function),
  );
});

it("submits the usage tab switches and blocks registration without collection", () => {
  renderForm("usage");
  fireEvent.click(screen.getByRole("checkbox", { name: "usageRegistrationRequired" }));
  submit();
  // Registration without collection is refused client-side; nothing is sent.
  expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("checkbox", { name: "usageCollectionReporting" }));
  submit();
  expect(save).toHaveBeenCalledWith(
    expect.any(String),
    expect.objectContaining({
      usage_collection_enabled: true,
      usage_registration_required: true,
      inventory_scan_enabled: false,
    }),
    "PUT",
    expect.any(Function),
  );
});

it("submits the retention tab without touching heartbeat fields", () => {
  renderForm("retention");
  fireEvent.change(screen.getByLabelText("telemetryLegalBasis"), {
    target: { value: "consent" },
  });
  submit();
  expect(save).toHaveBeenCalledWith(
    expect.any(String),
    expect.objectContaining({
      legal_basis: "consent",
      raw_retention_days: 90,
      aggregate_retention_days: 365,
      report_timezone: "UTC",
    }),
    "PUT",
    expect.any(Function),
  );
  const body = save.mock.calls[0]?.[1] as Record<string, unknown>;
  // Heartbeat fields merge from the known policy rather than the visible tab.
  expect(body).toMatchObject({ heartbeat_enabled: true, heartbeat_interval_seconds: 21600 });
});
