import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextIntlClientProvider } from "next-intl";
import messages from "../../messages/en.json";
import {
  EntityActionItems,
  usePreloadedEntityMenu,
} from "@/components/organisms/entity-action-items";
import { Button } from "@/components/atoms/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/atoms/menu";
import { queryEntityActionMenu } from "@/lib/entity-action-query";
import type { EntityActionSubject } from "@/lib/api/generated/types.gen";
import { loadCorporateGrantDialog, loadTechnologyOwnerEditor } from "@/actions/entity-actions";
import { corporateMutation } from "@/lib/api/corporate-mutation";
import { member } from "@/stories/UI Kit/Organisms/CorporateMemberRouteDialog.stories";

vi.mock("@/lib/entity-action-query", () => ({ queryEntityActionMenu: vi.fn() }));
vi.mock("@/components/organisms/contact-report-dialog", () => ({
  ContactReportDialog: () => null,
}));
vi.mock("@/components/organisms/corporate-resource-actions", () => ({
  CorporateResourceDeleteMenuItem: () => null,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/actions/object-presentation", () => ({ deleteObjectAction: vi.fn() }));
vi.mock("@/actions/entity-actions", () => ({
  loadCorporateGrantDialog: vi.fn(),
  loadTechnologyOwnerEditor: vi.fn(),
}));
vi.mock("@/lib/api/corporate-mutation", () => ({ corporateMutation: vi.fn() }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
  Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
const subject: EntityActionSubject = {
  kind: "team",
  id: "team_1",
  organization_id: "organization_1",
};
function Example({
  entity = subject,
  preload = false,
}: {
  entity?: EntityActionSubject;
  preload?: boolean;
}) {
  const initialResult = usePreloadedEntityMenu(preload ? entity : null);
  return (
    <NextIntlClientProvider locale="en" messages={messages}>
      <Menu>
        <MenuTrigger asChild>
          <Button>Actions</Button>
        </MenuTrigger>
        <MenuContent>
          <EntityActionItems
            initialResult={initialResult}
            subject={entity}
            entries={{
              edit: <MenuItem>Edit</MenuItem>,
              delete: <MenuItem>Delete</MenuItem>,
              open: <MenuItem>Open</MenuItem>,
            }}
          />
        </MenuContent>
      </Menu>
    </NextIntlClientProvider>
  );
}
const result = (ids: string[]) => ({
  menu: {
    subject,
    href: null,
    revision: null,
    authorization_revision: null,
    object_version: null,
    object_name: null,
    visibility: null,
    device_id: null,
    actions: ids.map((id) => ({ id, group: "management" as const })),
  },
  csrfToken: "csrf",
});

it("opens grant access over its originating card without navigation", async () => {
  const principal = {
    kind: "member" as const,
    id: member.account_id,
    organization_id: "organization_1",
  };
  vi.mocked(queryEntityActionMenu).mockResolvedValue({
    ...result(["manage_access"]),
    menu: { ...result(["manage_access"]).menu, subject: principal },
  });
  vi.mocked(loadCorporateGrantDialog).mockResolvedValue({
    organizationId: "organization_1",
    authorizationRevision: 1,
    csrfToken: "csrf",
    members: [member],
    initialMemberIds: [member.account_id],
    initialScope: undefined,
    roles: [],
    grantableRoleNames: ["staff"],
    teams: [],
    projects: [],
    scopeOptions: [],
    definitions: [],
    capabilities: ["grant.create"],
  });
  const origin = window.location.href;
  const user = userEvent.setup();
  render(<Example entity={principal} />);
  await user.click(screen.getByRole("button", { name: "Actions" }));
  await user.click(await screen.findByRole("menuitem", { name: messages.accessUi.grantAccess }));
  expect(await screen.findByRole("dialog", { name: messages.accessUi.grantAccess })).toBeVisible();
  expect(window.location.href).toBe(origin);
  expect(
    document.querySelector(`input[name="members"][value="${member.account_id}"]`),
  ).toBeChecked();
  await user.click(screen.getByRole("button", { name: messages.corporate.cancel }));
  expect(screen.queryByRole("dialog")).toBeNull();
  await user.click(screen.getByRole("menuitem", { name: messages.accessUi.grantAccess }));
  await screen.findByRole("dialog", { name: messages.accessUi.grantAccess });
  expect(
    document.querySelector(`input[name="members"][value="${member.account_id}"]`),
  ).toBeChecked();
});

it("opens component manage access over the catalog card", async () => {
  const principal = {
    kind: "component" as const,
    id: "component_1",
    organization_id: "organization_1",
  };
  vi.mocked(queryEntityActionMenu).mockResolvedValue({
    ...result(["manage_access"]),
    menu: { ...result(["manage_access"]).menu, subject: principal },
  });
  vi.mocked(loadCorporateGrantDialog).mockResolvedValue({
    organizationId: "organization_1",
    authorizationRevision: 1,
    csrfToken: "csrf",
    members: [member],
    initialMemberIds: [],
    initialScope: "catalog_object:component_1",
    roles: [],
    grantableRoleNames: null,
    teams: [],
    projects: [],
    scopeOptions: [{ value: "catalog_object:component_1", label: "Component" }],
    definitions: [],
    capabilities: ["binding.create"],
  });
  const origin = window.location.href;
  const user = userEvent.setup();
  render(<Example entity={principal} />);
  await user.click(screen.getByRole("button", { name: "Actions" }));
  await user.click(await screen.findByRole("menuitem", { name: messages.objects.manageAccess }));
  expect(await screen.findByRole("dialog", { name: messages.accessUi.grantAccess })).toBeVisible();
  expect(window.location.href).toBe(origin);
  expect(loadCorporateGrantDialog).toHaveBeenCalledWith(principal);
});

it("assigns a technology owner from its menu and closes after a successful write", async () => {
  const target = {
    kind: "technology" as const,
    id: "technology_1",
    organization_id: "organization_1",
  };
  vi.mocked(queryEntityActionMenu).mockResolvedValue({
    ...result(["change_owner"]),
    menu: { ...result(["change_owner"]).menu, subject: target },
  });
  vi.mocked(loadTechnologyOwnerEditor).mockResolvedValue({
    presentation: { revision: 2, authorization_revision: 3, owner_account_id: null } as never,
    members: [member],
    csrfToken: "csrf",
  });
  vi.mocked(corporateMutation).mockResolvedValue({ ok: true, data: {} });
  const user = userEvent.setup();
  render(<Example entity={target} />);
  await user.click(screen.getByRole("button", { name: "Actions" }));
  await user.click(await screen.findByRole("menuitem", { name: messages.hub.assignOwner }));
  expect(await screen.findByRole("dialog", { name: messages.hub.assignOwner })).toBeVisible();
  await user.selectOptions(screen.getByLabelText(messages.hub.operationalOwner), member.account_id);
  await user.click(screen.getByRole("button", { name: messages.corporate.update }));
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  expect(corporateMutation).toHaveBeenCalledWith(
    expect.objectContaining({
      path: "/v1/corporate/organizations/organization_1/technologies/technology_1/owner",
      method: "PUT",
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment -- Matcher inspects the typed request at the transport boundary.
      body: expect.objectContaining({
        owner_account_id: member.account_id,
        expected_revision: 2,
        authorization_revision: 3,
      }),
    }),
  );
});
describe("server entity actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  it("renders only server actions in server order and reloads after reopening", async () => {
    vi.mocked(queryEntityActionMenu)
      .mockResolvedValueOnce(result(["delete", "open"]))
      .mockResolvedValueOnce(result(["open"]));
    const user = userEvent.setup();
    render(<Example />);
    await user.click(screen.getByRole("button", { name: "Actions" }));
    await screen.findByRole("menuitem", { name: "Delete" });
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Delete",
      "Open",
    ]);
    expect(screen.queryByRole("menuitem", { name: "Edit" })).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Actions" }));
    await screen.findByRole("menuitem", { name: "Open" });
    expect(screen.queryByRole("menuitem", { name: "Delete" })).not.toBeInTheDocument();
    expect(queryEntityActionMenu).toHaveBeenCalledTimes(2);
  });
  it("shows a request failure and retries without inventing viewer permissions", async () => {
    vi.mocked(queryEntityActionMenu)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(result(["edit"]));
    const user = userEvent.setup();
    render(<Example />);
    await user.click(screen.getByRole("button", { name: "Actions" }));
    await user.click(
      await screen.findByRole("menuitem", {
        name: `${messages.common.requestFailed} ${messages.common.retry}`,
      }),
    );
    await screen.findByRole("menuitem", { name: "Edit" });
    await waitFor(() => {
      expect(queryEntityActionMenu).toHaveBeenCalledTimes(2);
    });
  });
});

it("preloads without exposing hidden actions, then revalidates when opened", async () => {
  vi.mocked(queryEntityActionMenu)
    .mockResolvedValueOnce(result(["edit"]))
    .mockResolvedValueOnce(result(["open"]));
  const user = userEvent.setup();
  render(<Example preload />);
  await waitFor(() => {
    expect(queryEntityActionMenu).toHaveBeenCalledTimes(1);
  });
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(screen.queryByRole("menuitem")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Actions" }));
  await screen.findByRole("menuitem", { name: "Open" });
  expect(screen.queryByRole("menuitem", { name: "Edit" })).not.toBeInTheDocument();
  expect(queryEntityActionMenu).toHaveBeenCalledTimes(2);
});
