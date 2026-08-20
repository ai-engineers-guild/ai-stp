import type { Meta, StoryObj } from "@storybook/react";

import { RouteLoading } from "@/components/molecules/route-loading";

const meta = {
  title: "UI Kit/Molecules/RouteLoading",
  component: RouteLoading,
  tags: ["autodocs"],
  args: {
    label: "Loading catalog…",
  },
} satisfies Meta<typeof RouteLoading>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
