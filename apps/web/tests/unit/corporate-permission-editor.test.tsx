import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { corporateMutationAction } from "@/actions/corporate";
import { CorporateRolePanel } from "@/components/organisms/corporate-role-panel";
import { CorporateMemberAccessPanel } from "@/components/organisms/corporate-member-access-panel";
import type { CorporatePermissionDefinition } from "@/lib/api/generated/types.gen";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/actions/corporate", () => ({
  corporateMutationAction: vi.fn().mockResolvedValue({ ok: true, data: {} }),
}));

const definitions = ["team.list", "team.create"].map((name) => ({
  name,
  resource: "team",
  group: "team",
  action: name.split(".")[1],
  scopes: ["organization"],
  implementation: "enforced",
  create_parent: null,
})) as CorporatePermissionDefinition[];

it("submits only selected catalog actions when creating a role", async () => {
  render(
    <CorporateRolePanel
      csrfToken="csrf"
      organizationId="organization_fixture"
      authorizationRevision={3}
      capabilities={["role.create"]}
      roles={[]}
      definitions={definitions}
      selected={null}
      labels={{
        createRole: "Create role",
        editRoleBody: "Edit",
        name: "Name",
        parentRole: "Parent role",
        permissions: "Permissions",
        create: "Create",
        creating: "Creating",
        update: "Update",
        saving: "Saving",
        delete: "Delete",
        deleting: "Deleting",
        deleteConfirm: "Delete?",
        saved: "Saved",
        failed: "Failed",
        none: "None",
      }}
    />,
  );
  fireEvent.click(screen.getByText("Create role"));
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "reviewer" } });
  fireEvent.click(screen.getByLabelText(/team.list/));
  fireEvent.click(screen.getByRole("button", { name: "Create" }));
  await waitFor(() => {
    expect(corporateMutationAction).toHaveBeenCalled();
  });
  expect(vi.mocked(corporateMutationAction).mock.calls[0]?.[0].body).toMatchObject({
    permissions: ["team.list"],
  });
});

it("limits direct grant choices to caller actions valid for the chosen scope", () => {
  render(
    <CorporateMemberAccessPanel
      csrfToken="csrf"
      organizationId="organization_fixture"
      authorizationRevision={3}
      accountId="account_fixture"
      teams={[{ team_id: "team_fixture", name: "Platform" } as never]}
      projects={[]}
      roles={[]}
      grantableRoleNames={[]}
      bindings={[]}
      grants={[]}
      capabilities={["binding.create", "team.list", "team.create"]}
      definitions={definitions.map((definition) => ({
        ...definition,
        scopes: [definition.action === "list" ? "organization" : "team"],
      }))}
      labels={{
        bindings: "Bindings",
        team: "Team",
        project: "Project",
        role: "Role",
        scope: "Scope",
        organization: "Organization",
        operation: "Operation",
        assign: "Assign",
        remove: "Remove",
        create: "Create",
        creating: "Creating",
        revoke: "Revoke",
        revoking: "Revoking",
        coverage: "Coverage",
        coverageSelf: "Self",
        coverageDescendants: "Descendants",
        originMembership: "Membership",
        originAssignment: "Assignment",
        originDirect: "Direct",
        originServicePrincipal: "Service",
        noBindings: "No bindings",
        directGrants: "Direct grants",
        directGrantsBody: "Body",
        grantAction: "Grant action",
        permission: "Permission",
        issuer: "Issuer",
        noGrants: "No grants",
        saved: "Saved",
        targetRequired: "Target required",
        assignments: "Assignments",
        update: "Update",
        confirmRevoke: "Revoke?",
      }}
    />,
  );
  const grantSummary = screen
    .getAllByText("Grant action")
    .find((element) => element.tagName === "SUMMARY");
  if (!grantSummary) throw new Error("Grant action disclosure is missing");
  fireEvent.click(grantSummary);
  const permission = screen.getByLabelText("Permission");
  expect(permission).toHaveTextContent("team.list");
  expect(permission).not.toHaveTextContent("team.create");
  fireEvent.change(screen.getByLabelText("Scope"), { target: { value: "team:team_fixture" } });
  expect(permission).toHaveTextContent("team.create");
  expect(permission).not.toHaveTextContent("team.list");
});
