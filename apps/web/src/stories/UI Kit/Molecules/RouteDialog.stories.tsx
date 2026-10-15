import type { Meta, StoryObj } from "@storybook/react";
import { RouteDialog } from "@/components/molecules/route-dialog";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
const meta = {
  title: "UI Kit/Molecules/RouteDialog",
  component: RouteDialog,
  tags: ["autodocs"],
} satisfies Meta<typeof RouteDialog>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Create: Story = {
  args: {
    title: "Add project",
    children: (
      <>
        <Label htmlFor="route-project">Project name</Label>
        <Input id="route-project" />
      </>
    ),
  },
};
