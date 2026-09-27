import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

const save = vi.hoisted(() => vi.fn());
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: { count?: number }) =>
    values?.count !== undefined ? `${key}:${values.count}` : key,
}));
vi.mock("@/components/organisms/corporate-governance-controls", () => ({
  useGovernanceMutation: () => ({ busy: false, message: null, save }),
}));

import { CorporateTelemetryPolicyControls } from "@/components/organisms/corporate-telemetry-policy-controls";

function renderForm() {
  render(
    <CorporateTelemetryPolicyControls
      policy={null}
      organizationId="organization_test"
      authorizationRevision={7}
      csrfToken="csrf"
    />,
  );
  fireEvent.change(screen.getByLabelText("telemetryLegalBasis"), {
    target: { value: "consent" },
  });
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

it("submits toggle switches as boolean strings", () => {
  renderForm();
  // The heartbeat switch starts enabled (policy fallback); uncheck it.
  fireEvent.click(screen.getByRole("checkbox", { name: "heartbeatReporting" }));
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
