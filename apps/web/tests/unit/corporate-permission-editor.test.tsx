import { fireEvent, render as renderComponent, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import messages from "../../messages/en.json";
import { expect, it, vi } from "vitest";

import { corporateMutation } from "@/lib/api/corporate-mutation";
import { CorporateRolePanel } from "@/components/organisms/corporate-role-panel";
import { CorporateMemberAccessPanel } from "@/components/organisms/corporate-member-access-panel";
import type {
  CorporatePermissionDefinition,
  CorporateRoleView,
} from "@/lib/api/generated/types.gen";
import {
  entityDefinitions,
  permissionColumn,
  rolePermissions,
} from "@/lib/corporate-permission-ui";

const render = (ui: ReactNode) =>
  renderComponent(
    <NextIntlClientProvider locale="en" messages={messages}>
      {ui}
    </NextIntlClientProvider>,
  );

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/lib/api/corporate-mutation", () => ({
  corporateMutation: vi.fn().mockResolvedValue({ ok: true, data: {} }),
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
      definitions={definitions}
      selected={null}
      labels={{
        name: "Name",
        permissions: "Permissions",
        create: "Create",
        creating: "Creating",
        update: "Update",
        saving: "Saving",
        saved: "Saved",
        failed: "Failed",
      }}
    />,
  );
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "reviewer" } });
  fireEvent.click(screen.getByLabelText(/team.list/));
  fireEvent.click(screen.getByRole("button", { name: "Create" }));
  await waitFor(() => {
    expect(corporateMutation).toHaveBeenCalled();
  });
  expect(vi.mocked(corporateMutation).mock.calls[0]?.[0].body).toMatchObject({
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
        teamRole: "Team role",
        projectRole: "Project role",
        projectRoleHint: "Project hint",
        projectRoleOwner: "Owner",
        projectRoleContributor: "Contributor",
        roleLead: "Lead",
        roleStaff: "Staff",
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
  expect(permission.querySelector('option[value="team.list"]')).not.toBeNull();
  expect(permission.querySelector('option[value="team.create"]')).toBeNull();
  fireEvent.change(screen.getByLabelText("Scope"), { target: { value: "team:team_fixture" } });
  expect(permission.querySelector('option[value="team.create"]')).not.toBeNull();
  expect(permission.querySelector('option[value="team.list"]')).toBeNull();
});

it("keeps relationship actions in their entity and resolves inherited permissions without cycles", () => {
  const relation = {
    ...definitions[0],
    name: "project_team.link",
    resource: "project_team",
    action: "link",
  } as CorporatePermissionDefinition;
  expect(
    entityDefinitions([...definitions, relation]).find(([entity]) => entity === "project")?.[1],
  ).toEqual([relation]);
  expect(permissionColumn(relation)).toBe("other");
  const roles: [CorporateRoleView, CorporateRoleView] = [
    {
      schema_version: 1,
      name: "child",
      parent_role: "parent",
      permissions: ["team.create"],
      revision: 1,
    },
    {
      schema_version: 1,
      name: "parent",
      parent_role: "child",
      permissions: ["team.list"],
      revision: 1,
    },
  ];
  expect([...rolePermissions(roles[0], roles)].sort()).toEqual(["team.create", "team.list"]);
});
