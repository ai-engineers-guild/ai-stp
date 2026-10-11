import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CorporateServicePrincipalsPanel } from "@/components/organisms/corporate-service-principals-panel";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock("@/lib/api/corporate-mutation", () => ({
  corporateMutation: vi.fn(),
}));

afterEach(cleanup);

const labels = {
  title: "Service principals",
  name: "Name",
  role: "Role",
  scope: "Scope",
  organization: "Organization",
  team: "Team",
  project: "Project",
  create: "Create",
  creating: "Creating…",
  activate: "Activate",
  suspend: "Suspend",
  delete: "Delete",
  deleting: "Deleting…",
  confirmDelete: "Delete this service principal?",
  noServicePrincipals: "No service principals.",
  saved: "Saved.",
  failed: "Failed.",
};

it("labels the create-form name field as Name, not the section title", () => {
  render(
    <CorporateServicePrincipalsPanel
      csrfToken="csrf"
      organizationId="org_1"
      authorizationRevision={1}
      roles={[]}
      servicePrincipals={[]}
      teams={[]}
      projects={[]}
      capabilities={["service_principal.manage", "service_principal.list"]}
      labels={labels}
    />,
  );
  expect(screen.getByLabelText("Name")).toBeVisible();
});
