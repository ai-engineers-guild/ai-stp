import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import { corporateMutationAction, corporateTeamAssignmentsAction } from "@/actions/corporate";
import { CorporateResourceActions } from "@/components/organisms/corporate-resource-actions";
import { CorporateTeamEditor } from "@/components/organisms/corporate-team-editor";
import { CorporateTeamMemberships } from "@/components/organisms/corporate-team-memberships";
import { CorporateEmployeeDirectory } from "@/components/organisms/corporate-employee-directory";
import type { CorporateMember, CorporateTeamView } from "@/lib/api/generated/types.gen";
import type { ReactNode } from "react";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push }) }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh, push }),
  Link: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
vi.mock("@/actions/corporate", () => ({
  corporateMutationAction: vi.fn(),
  corporateTeamAssignmentsAction: vi.fn(),
}));

const employee: CorporateMember = {
  schema_version: 1,
  account_id: "account_A",
  display_name: "Alice",
  role: "staff",
  state: "active",
  revision: 1,
};
const bob: CorporateMember = { ...employee, account_id: "account_B", display_name: "Bob" };
const team: CorporateTeamView = {
  schema_version: 1,
  team_id: "operation_A",
  organization_id: "organization_A",
  name: "Support",
  description: "Helping customers",
  state: "active",
  revision: 1,
  members: [employee],
  lead_account_ids: [employee.account_id],
};
const second: CorporateTeamView = {
  ...team,
  team_id: "operation_B",
  name: "Engineering",
  members: [],
  lead_account_ids: [],
};
const common = { csrfToken: "csrf", organizationId: "organization_A", canManage: true };
function wrap(children: ReactNode) {
  return (
    <NextIntlClientProvider locale="en" messages={messages}>
      {children}
    </NextIntlClientProvider>
  );
}

describe("corporate team workspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(corporateMutationAction).mockResolvedValue({ ok: true, data: team });
    vi.mocked(corporateTeamAssignmentsAction).mockImplementation((input) =>
      Promise.resolve({ completed: input.assignments.map((item) => item.idempotencyKey) }),
    );
  });
  it("opens editing explicitly, cancels without saving, then archives persisted values", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    render(wrap(<CorporateTeamEditor {...common} team={team} authorizationRevision={1} />));
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Unsaved name");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(corporateMutationAction).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Archive team" }));
    await waitFor(() => {
      expect(corporateMutationAction).toHaveBeenCalled();
      expect(vi.mocked(corporateMutationAction).mock.calls[0]?.[0].body).toMatchObject({
        name: "Support",
        description: "Helping customers",
        state: "archived",
      });
    });
  });
  it("selects unassigned employees and adds a team lead", async () => {
    const user = userEvent.setup();
    render(
      wrap(
        <CorporateTeamMemberships
          {...common}
          team={team}
          teams={[team, second]}
          members={[employee, bob]}
        />,
      ),
    );
    expect(screen.getByText("Alice")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add employees" }));
    await user.selectOptions(screen.getByLabelText("Team membership"), "unassigned");
    await user.type(screen.getByLabelText("Search employees"), "Bob");
    await user.click(screen.getByRole("checkbox", { name: /Bob/ }));
    await user.selectOptions(screen.getByLabelText("Role in this team"), "lead");
    await user.click(screen.getByRole("button", { name: "Add selected (1)" }));
    await waitFor(() => {
      expect(corporateTeamAssignmentsAction).toHaveBeenCalled();
      expect(
        vi.mocked(corporateTeamAssignmentsAction).mock.calls[0]?.[0].assignments,
      ).toMatchObject([
        { accountId: bob.account_id, teamId: team.team_id, role: "lead", operation: "assign" },
      ]);
    });
  });
  it("assigns multiple teams from employee details and retains unfinished selection", async () => {
    const user = userEvent.setup();
    vi.mocked(corporateTeamAssignmentsAction).mockImplementation((input) =>
      Promise.resolve({
        completed: input.assignments.slice(0, 1).map((item) => item.idempotencyKey),
        message: "Conflict",
      }),
    );
    render(
      wrap(
        <CorporateTeamMemberships
          {...common}
          employee={bob}
          teams={[team, second]}
          members={[employee, bob]}
        />,
      ),
    );
    await user.click(screen.getByRole("button", { name: "Choose teams" }));
    await user.click(screen.getByRole("checkbox", { name: /Support/ }));
    await user.click(screen.getByRole("checkbox", { name: /Engineering/ }));
    await user.click(screen.getByRole("button", { name: "Add selected (2)" }));
    await screen.findByRole("status");
    expect(screen.getByRole("checkbox", { name: /Support/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Engineering/ })).toBeChecked();
    expect(refresh).toHaveBeenCalled();
  });
  it("shows archived and empty states, permits removal but hides adding", () => {
    render(
      wrap(
        <CorporateTeamMemberships
          {...common}
          team={{ ...team, state: "archived" }}
          teams={[team]}
          members={[employee]}
        />,
      ),
    );
    expect(screen.queryByRole("button", { name: "Add employees" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove from team" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Make staff" })).not.toBeInTheDocument();
  });
  it("filters the employee directory by team and unassigned membership", async () => {
    const user = userEvent.setup();
    render(wrap(<CorporateEmployeeDirectory members={[employee, bob]} teams={[team, second]} />));
    await user.selectOptions(screen.getByLabelText("Filter by team"), "unassigned");
    expect(screen.queryByText("Alice")).not.toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Filter by team"), team.team_id);
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.queryByText("Bob")).not.toBeInTheDocument();
  });
  it("discards cancelled role permissions on reopen", async () => {
    const user = userEvent.setup();
    render(
      wrap(
        <CorporateResourceActions
          csrfToken="csrf"
          organizationId="organization_A"
          authorizationRevision={1}
          resource="roles"
          resourceId="auditor"
          name="auditor"
          parentRole="staff"
          rolePermissions={["team.read"]}
          state="base"
          revision={1}
          permissions={["role.update"]}
          labels={{ ...messages.corporate, title: "Actions" }}
        />,
      ),
    );
    await user.click(screen.getByRole("button", { name: "Actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    await user.clear(screen.getByLabelText(messages.corporate.parentRole));
    await user.type(screen.getByLabelText(messages.corporate.parentRole), "superadmin");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    expect(screen.getByLabelText(messages.corporate.parentRole)).toHaveValue("staff");
    expect(screen.getByLabelText(messages.corporate.permissions)).toHaveValue("team.read");
  });
  it("hides management controls for read-only users", () => {
    render(
      wrap(
        <CorporateTeamMemberships
          {...common}
          canManage={false}
          team={team}
          teams={[team]}
          members={[]}
        />,
      ),
    );
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
