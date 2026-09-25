import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

const context = vi.hoisted(() => ({
  capabilities: ["telemetry.read", "telemetry.manage"],
  organization: { organization_id: "organization_test", authorization_revision: 7 },
}));
const readPolicy = vi.hoisted(() =>
  vi.fn(() => Promise.resolve({ heartbeat_interval_seconds: 60 })),
);

vi.mock("next-intl/server", () => ({
  getTranslations: () => Promise.resolve((key: string) => key),
  setRequestLocale: vi.fn(),
}));
vi.mock("@/lib/auth/require-session", () => ({
  requireSession: vi.fn(),
  sessionCookieValue: () => Promise.resolve("session"),
}));
vi.mock("@/lib/auth/session", () => ({ readCsrfToken: () => Promise.resolve("csrf") }));
vi.mock("@/lib/api/corporate", () => ({ readCorporateContext: () => Promise.resolve(context) }));
vi.mock("@/lib/api/technology", () => ({
  readTechnologyCapabilities: () =>
    Promise.resolve({
      capabilities: ["landscape.manage", "landscape.read"],
      authorization_revision: "projection-revision",
    }),
  readTechnologyLandscapePolicy: () => Promise.resolve({}),
}));
vi.mock("@/lib/api/http", () => ({ apiRequest: readPolicy }));
vi.mock("@/components/organisms/corporate-governance-controls", () => ({
  TechnologyActivityPolicy: () => <div>Landscape policy</div>,
}));
vi.mock("@/components/organisms/corporate-telemetry-policy-controls", () => ({
  CorporateTelemetryPolicyControls: ({
    authorizationRevision,
  }: {
    authorizationRevision: number;
  }) => <div data-testid="heartbeat-policy" data-revision={authorizationRevision} />,
}));
vi.mock("@/components/molecules/history-back-button", () => ({ HistoryBackButton: () => null }));

import CorporateSettingsPage from "@/app/[locale]/(site)/corporate/organization/admins/settings/page";

it("shows heartbeat settings from corporate telemetry rights and passes the numeric policy revision", async () => {
  const page = await CorporateSettingsPage({ params: Promise.resolve({ locale: "en" }) });
  render(page);
  expect(screen.getByTestId("heartbeat-policy")).toHaveAttribute("data-revision", "7");
  expect(
    screen
      .getByTestId("heartbeat-policy")
      .compareDocumentPosition(screen.getByText("Landscape policy")) &
      Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(readPolicy).toHaveBeenCalledWith(
    "/v1/corporate/organizations/organization_test/telemetry/policy",
    { sessionToken: "session" },
  );
});
