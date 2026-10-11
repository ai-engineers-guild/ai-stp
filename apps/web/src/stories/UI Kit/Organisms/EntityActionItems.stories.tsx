import type { Meta, StoryObj } from "@storybook/react";
import { EntityActionItems } from "@/components/organisms/entity-action-items";
import { Menu, MenuContent, MenuTrigger } from "@/components/atoms/menu";
import { Button } from "@/components/atoms/button";
import { withAppChrome } from "@/stories/decorators";
function Example() {
  return (
    <Menu defaultOpen>
      <MenuTrigger asChild>
        <Button>Entity actions</Button>
      </MenuTrigger>
      <MenuContent>
        <EntityActionItems
          subject={{ kind: "team", id: "team_example", organization_id: "organization_example" }}
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
