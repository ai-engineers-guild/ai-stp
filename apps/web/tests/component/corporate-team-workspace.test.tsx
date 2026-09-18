import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../messages/en.json";
import { corporateMutationAction, corporateTeamAssignmentsAction } from "@/actions/corporate";
import { CorporateResourceActions } from "@/components/organisms/corporate-resource-actions";
import { ProjectionDockView } from "@/components/molecules/projection-dock-view";
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
  job_title_id: null,
  job_title_name: null,
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
  assignments: [],
  effective_assignments: [],
  effective_permissions: [],
  governance_history: [],
  maintained_catalog_objects: [],
  owned_catalog_objects: [],
  project_ids: [],
  technology_ids: [],
  available_actions: [],
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
    expect(screen.getByRole("option", { name: "Not assigned" })).toHaveValue("available");
    expect(screen.getByRole("option", { name: "All teams" })).toHaveValue("all");
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
  it("reuses a failed resource effect key but changes it for an edited draft", async () => {
    const user = userEvent.setup();
    vi.mocked(corporateMutationAction).mockResolvedValue({ ok: false, message: "Conflict" });
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
    await user.click(screen.getByRole("button", { name: messages.corporate.update }));
    await screen.findByText("Conflict");
    await user.click(screen.getByRole("button", { name: messages.corporate.update }));
    await waitFor(() => {
      expect(corporateMutationAction).toHaveBeenCalledTimes(2);
    });
    expect(vi.mocked(corporateMutationAction).mock.calls[1]?.[0].body).toEqual(
      vi.mocked(corporateMutationAction).mock.calls[0]?.[0].body,
    );
    await user.clear(screen.getByLabelText(messages.corporate.parentRole));
    await user.type(screen.getByLabelText(messages.corporate.parentRole), "lead");
    await user.click(screen.getByRole("button", { name: messages.corporate.update }));
    await waitFor(() => {
      expect(corporateMutationAction).toHaveBeenCalledTimes(3);
    });
    expect(vi.mocked(corporateMutationAction).mock.calls[2]?.[0].body).not.toMatchObject({
      idempotency_key: (
        vi.mocked(corporateMutationAction).mock.calls[0]?.[0].body as { idempotency_key: string }
      ).idempotency_key,
    });
  });
  it("retains the resource draft and operation key after a transport failure", async () => {
    const user = userEvent.setup();
    vi.mocked(corporateMutationAction)
      .mockRejectedValueOnce(new Error("Connection lost"))
      .mockResolvedValueOnce({ ok: false, message: "Conflict" });
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
    await user.type(screen.getByLabelText(messages.corporate.parentRole), "lead");
    await user.click(screen.getByRole("button", { name: messages.corporate.update }));
    await screen.findByText(messages.common.apiUnavailable);
    expect(screen.getByLabelText(messages.corporate.parentRole)).toHaveValue("lead");
    expect(screen.getByRole("button", { name: messages.corporate.update })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: messages.corporate.update }));
    await screen.findByText("Conflict");
    expect(vi.mocked(corporateMutationAction).mock.calls[1]?.[0].body).toEqual(
      vi.mocked(corporateMutationAction).mock.calls[0]?.[0].body,
    );
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

describe("corporate projection placement", () => {
  it.each([
    ["/en/corporate/teams/team_A?filter=all", "inline"],
    ["/en/login?next=/en/corporate", "fixed"],
  ])("uses only the path of %s", (humanHref, placement) => {
    render(
      <ProjectionDockView
        projection="human"
        humanHref={humanHref}
        machineHref="/en/ai"
        labels={{ group: "Site format", human: "Human", machine: "Machine" }}
      />,
    );
    expect(screen.getByRole("complementary", { name: "Site format" })).toHaveAttribute(
      "data-placement",
      placement,
    );
  });
});
