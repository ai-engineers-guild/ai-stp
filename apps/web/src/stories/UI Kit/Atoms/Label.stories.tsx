import type { Meta, StoryObj } from "@storybook/react";

import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";

const meta = {
  title: "UI Kit/Atoms/Label",
  component: Label,
  tags: ["autodocs"],
} satisfies Meta<typeof Label>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    children: "Display name",
    htmlFor: "label-demo",
  },
  render: (args) => (
    <div className="flex max-w-sm flex-col gap-2">
      <Label {...args} />
      <Input id="label-demo" placeholder="Value" />
    </div>
  ),
};
