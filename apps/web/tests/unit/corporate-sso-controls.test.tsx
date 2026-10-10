import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const save = vi.hoisted(() => vi.fn());
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: { providers?: string }) =>
    values?.providers !== undefined ? `${key}:${values.providers}` : key,
}));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, ...props }: React.ComponentProps<"a">) => <a {...props}>{children}</a>,
}));
vi.mock("@/components/organisms/corporate-governance-controls", () => ({
  useGovernanceMutation: () => ({ busy: false, message: null, save }),
}));

import { CorporateSsoControls } from "@/components/organisms/corporate-sso-controls";
import type { CorporateSsoView } from "@/lib/api/corporate-sso";

const AUTHORITY = {
  organizationId: "organization_test",
  authorizationRevision: 7,
  csrfToken: "csrf",
};

const VIEW: CorporateSsoView = {
  providers: [
    {
      provider: "saml",
      enabled: false,
      issuer_url: null,
      client_id: null,
      idp_metadata_url: null,
      updated_at: null,
    },
    {
      provider: "oidc",
      enabled: true,
      issuer_url: "https://sso.example.com/realms/org",
      client_id: "ai-stp",
      idp_metadata_url: null,
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
};

beforeEach(() => save.mockClear());

it("renders both provider cards with their configured state", () => {
  render(<CorporateSsoControls {...AUTHORITY} sso={VIEW} />);
  expect(screen.getByText("ssoProviders.saml.title")).toBeVisible();
  expect(screen.getByText("ssoProviders.oidc.title")).toBeVisible();
  expect(screen.getByText("ssoNotConfigured")).toBeVisible();
  expect(screen.getByText("ssoEnabled")).toBeVisible();
  // The enabled OIDC provider shows its issuer and client id.
  expect(screen.getByLabelText("ssoIssuerUrl")).toHaveValue("https://sso.example.com/realms/org");
  expect(screen.getByLabelText("ssoClientId")).toHaveValue("ai-stp");
});

it("submits the toggled provider configuration", () => {
  render(<CorporateSsoControls {...AUTHORITY} sso={VIEW} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "ssoEnable ssoProviders.saml.title" }));
  fireEvent.change(screen.getByLabelText("ssoIdpMetadataUrl"), {
    target: { value: "https://idp.example.com/metadata" },
  });
  const form = screen.getAllByRole("button", { name: "saveChanges" })[0]?.closest("form");
  if (!form) throw new Error("sso form is missing");
  fireEvent.submit(form);
  expect(save).toHaveBeenCalledWith(
    "/v1/corporate/organizations/organization_test/sso",
    expect.objectContaining({
      provider: "saml",
      enabled: true,
      idp_metadata_url: "https://idp.example.com/metadata",
    }),
    "PUT",
    expect.any(Function),
  );
});

it("renders disabled cards and the deployment note when the endpoint is absent", () => {
  render(
    <CorporateSsoControls
      {...AUTHORITY}
      sso={null}
      deploymentProviders={["Authentik", "Keycloak"]}
    />,
  );
  expect(screen.getByText("ssoUnavailableWithProviders:Authentik, Keycloak")).toBeVisible();
  for (const checkbox of screen.getAllByRole("checkbox")) {
    expect(checkbox).toBeDisabled();
  }
  expect(screen.queryByRole("button", { name: "saveChanges" })).toBeNull();
});

it("hides the save button without the manage capability", () => {
  render(<CorporateSsoControls {...AUTHORITY} sso={VIEW} canManage={false} />);
  expect(screen.queryByRole("button", { name: "saveChanges" })).toBeNull();
});
