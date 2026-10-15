import type { Meta, StoryObj } from "@storybook/react";
import { EntityActionItems } from "@/components/organisms/entity-action-items";
import { Menu, MenuContent, MenuTrigger } from "@/components/atoms/menu";
import { Button } from "@/components/atoms/button";
import { withAppChrome } from "@/stories/decorators";
function Example({ action }: { action?: "manage_access" | "change_owner" }) {
  const subject = {
    kind: action === "change_owner" ? ("technology" as const) : ("member" as const),
    id: "account_example",
    organization_id: "organization_example",
  };
  return (
    <Menu defaultOpen>
      <MenuTrigger asChild>
        <Button>Entity actions</Button>
      </MenuTrigger>
      <MenuContent>
        <EntityActionItems
          subject={subject}
          {...(action
            ? {
                initialResult: {
                  csrfToken: "storybook",
                  menu: {
                    subject,
                    href: null,
                    revision: 0,
                    authorization_revision: 0,
                    object_version: null,
                    object_name: null,
                    visibility: null,
                    device_id: null,
                    actions: [{ id: action, group: "management" as const }],
                  },
                },
              }
            : {})}
          entries={{}}
        />
      </MenuContent>
    </Menu>
  );
}
const meta = {
  title: "UI Kit/Organisms/EntityActionItems",
  component: Example,
  decorators: [withAppChrome],
  tags: ["autodocs"],
} satisfies Meta<typeof Example>;
export default meta;
type Story = StoryObj<typeof meta>;
export const ServerOrder: Story = {};
export const GrantOnCurrentPage: Story = { args: { action: "manage_access" } };
export const TechnologyOwner: Story = { args: { action: "change_owner" } };
