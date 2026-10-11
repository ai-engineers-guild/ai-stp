import { renderToString } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: { count?: number; value?: string }) =>
    values?.count !== undefined ? `${key}:${values.count}` : key,
}));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, ...props }: React.ComponentProps<"a">) => <a {...props}>{children}</a>,
}));
vi.mock("@/components/organisms/corporate-governance-controls", () => ({
  useGovernanceMutation: () => ({ busy: false, message: null, save: vi.fn() }),
}));

import { CorporateTelemetryPolicyControls } from "@/components/organisms/corporate-telemetry-policy-controls";

const props = {
  policy: null,
  organizationId: "organization_test",
  authorizationRevision: 7,
  csrfToken: "csrf",
} as const;

for (const tab of ["heartbeat", "usage", "retention"] as const) {
  it(`SSR renders the ${tab} tab`, () => {
    const html = renderToString(<CorporateTelemetryPolicyControls {...props} tab={tab} />);
    expect(html.length).toBeGreaterThan(0);
  });
}
