import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

const save = vi.hoisted(() => vi.fn());
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("@/components/organisms/corporate-governance-controls", () => ({
  useGovernanceMutation: () => ({ busy: false, message: null, save }),
}));

import { CorporateTelemetryPolicyControls } from "@/components/organisms/corporate-telemetry-policy-controls";

it("submits a one-minute heartbeat interval with the corporate policy revision", () => {
  render(
    <CorporateTelemetryPolicyControls
      policy={null}
      organizationId="organization_test"
      authorizationRevision={7}
      csrfToken="csrf"
    />,
  );
  expect(screen.getByLabelText("heartbeatIntervalSeconds")).toHaveAttribute("min", "60");
  fireEvent.change(screen.getByLabelText("telemetryLegalBasis"), {
    target: { value: "consent" },
  });
  fireEvent.change(screen.getByLabelText("heartbeatIntervalSeconds"), {
    target: { value: "60" },
  });
  const form = screen.getByRole("button", { name: "saveChanges" }).closest("form");
  expect(form).not.toBeNull();
  if (!form) throw new Error("telemetry policy form is missing");
  fireEvent.submit(form);
  expect(save).toHaveBeenCalledWith(
    "/v1/corporate/organizations/organization_test/telemetry/policy",
    expect.objectContaining({ heartbeat_interval_seconds: 60, expected_policy_revision: 0 }),
    "PUT",
    expect.any(Function),
  );
});
