import type { Meta, StoryObj } from "@storybook/react";

import { Label } from "@/components/atoms/label";
import { Select } from "@/components/atoms/select";

const meta = {
  title: "UI Kit/Atoms/Select",
  component: Select,
  tags: ["autodocs"],
  args: {
    "aria-label": "Team",
    children: (
      <>
        <option value="">All teams</option>
        <option value="ops">Operations</option>
        <option value="eng">Engineering</option>
      </>
    ),
  },
} satisfies Meta<typeof Select>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithLabel: Story = {
  render: (args) => (
    <div className="grid max-w-xs gap-2">
      <Label htmlFor="team">Team</Label>
      <Select id="team" {...args} />
    </div>
  ),
};

export const Disabled: Story = {
  args: { disabled: true },
};

export const InlineWidth: Story = {
  args: { className: "sm:w-auto sm:min-w-32" },
};
