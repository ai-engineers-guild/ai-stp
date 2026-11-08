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
      {/* biome-ignore lint/a11y/noLabelWithoutControl: The story label and input share the same customizable htmlFor/id expression. */}
      <Label {...args} htmlFor={args.htmlFor ?? "label-demo"} />
      <Input id={args.htmlFor ?? "label-demo"} placeholder="Value" />
    </div>
  ),
};
