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

vi.mock("@/lib/entity-action-query", () => ({ queryEntityActionMenu: vi.fn() }));
vi.mock("@/components/organisms/contact-report-dialog", () => ({
  ContactReportDialog: () => null,
}));
vi.mock("@/components/organisms/corporate-resource-actions", () => ({
  CorporateResourceDeleteMenuItem: () => null,
}));
vi.mock("@/actions/object-presentation", () => ({ deleteObjectAction: vi.fn() }));
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
