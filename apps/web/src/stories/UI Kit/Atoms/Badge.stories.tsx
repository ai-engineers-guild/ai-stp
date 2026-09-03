import type { Meta, StoryObj } from "@storybook/react";

import { Badge } from "@/components/atoms/badge";

const meta = {
  title: "UI Kit/Atoms/Badge",
  component: Badge,
  tags: ["autodocs"],
  args: { children: "experimental" },
} satisfies Meta<typeof Badge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const AllVariants: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <Badge variant="default">default</Badge>
      <Badge variant="secondary">secondary</Badge>
      <Badge variant="outline">outline</Badge>
      <Badge variant="success">authoritative</Badge>
      <Badge variant="warning">warning</Badge>
      <Badge variant="destructive">failed</Badge>
    </div>
  ),
};
