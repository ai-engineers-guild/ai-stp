import type { Meta, StoryObj } from "@storybook/react";

import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";

const meta = {
  title: "UI Kit/Atoms/Textarea",
  component: Textarea,
  tags: ["autodocs"],
} satisfies Meta<typeof Textarea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    placeholder: "Bio",
    "aria-label": "Bio",
    rows: 4,
  },
};

export const WithLabel: Story = {
  render: () => (
    <div className="flex max-w-md flex-col gap-2">
      <Label htmlFor="story-bio">Bio</Label>
      <Textarea id="story-bio" rows={4} placeholder="Short public bio" />
    </div>
  ),
};
