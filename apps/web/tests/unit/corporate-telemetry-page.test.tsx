import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

const context = vi.hoisted(() => ({
  capabilities: ["telemetry.read", "telemetry.manage"],
  member: { role: "superadmin" },
  organization: { organization_id: "organization_test", authorization_revision: 7 },
}));
const readPolicy = vi.hoisted(() =>
  vi.fn(() => Promise.resolve({ policy_version: 3, heartbeat_interval_seconds: 60 })),
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
vi.mock("@/lib/api/http", () => ({ apiRequest: readPolicy }));
vi.mock("@/components/organisms/corporate-telemetry-policy-controls", () => ({
  CorporateTelemetryPolicyControls: (props: {
    authorizationRevision: number;
    tab: string;
    canManage: boolean;
    policy: unknown;
  }) => (
    <div
      data-testid="telemetry-controls"
      data-revision={props.authorizationRevision}
      data-tab={props.tab}
      data-manage={String(props.canManage)}
      data-policy={JSON.stringify(props.policy)}
    />
  ),
}));
vi.mock("@/app/[locale]/(site)/corporate/admin/people-shared", () => ({
  PeopleHeader: () => null,
}));

import CorporateTelemetryPage from "@/app/[locale]/(site)/corporate/admin/telemetry/page";

const params = Promise.resolve({ locale: "en" });
const search = (tab?: string) => Promise.resolve(tab ? { tab } : {});

it("loads the organization telemetry policy and forwards revision, tab, and manage rights", async () => {
  const page = await CorporateTelemetryPage({ params, searchParams: search("usage") });
  render(page);
  const controls = screen.getByTestId("telemetry-controls");
  expect(controls).toHaveAttribute("data-revision", "7");
  expect(controls).toHaveAttribute("data-tab", "usage");
  expect(controls).toHaveAttribute("data-manage", "true");
  expect(controls).toHaveAttribute(
    "data-policy",
    JSON.stringify({ policy_version: 3, heartbeat_interval_seconds: 60 }),
  );
  expect(readPolicy).toHaveBeenCalledWith(
    "/v1/corporate/organizations/organization_test/telemetry/policy",
    { sessionToken: "session" },
  );
});

it("defaults to the heartbeat tab and rejects unknown tab values", async () => {
  const page = await CorporateTelemetryPage({ params, searchParams: search("bogus") });
  render(page);
  expect(screen.getByTestId("telemetry-controls")).toHaveAttribute("data-tab", "heartbeat");
});

it("renders read-only controls for telemetry.read without telemetry.manage", async () => {
  context.capabilities = ["telemetry.read"];
  const page = await CorporateTelemetryPage({ params, searchParams: search() });
  render(page);
  expect(screen.getByTestId("telemetry-controls")).toHaveAttribute("data-manage", "false");
  context.capabilities = ["telemetry.read", "telemetry.manage"];
});
