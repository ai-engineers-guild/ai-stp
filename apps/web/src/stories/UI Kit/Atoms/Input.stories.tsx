import type { Meta, StoryObj } from "@storybook/react";

import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";

const meta = {
  title: "UI Kit/Atoms/Input",
  component: Input,
  tags: ["autodocs"],
} satisfies Meta<typeof Input>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    placeholder: "Search components…",
    "aria-label": "Search",
  },
};

export const WithLabel: Story = {
  render: () => (
    <div className="flex max-w-sm flex-col gap-2">
      <Label htmlFor="story-input">Display name</Label>
      <Input id="story-input" placeholder="Ada Lovelace" />
    </div>
  ),
};
