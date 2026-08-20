import type { Meta, StoryObj } from "@storybook/react";

import { ThemeToggle } from "@/components/molecules/theme-toggle";

const meta = {
  title: "UI Kit/Molecules/ThemeToggle",
  component: ThemeToggle,
  tags: ["autodocs"],
} satisfies Meta<typeof ThemeToggle>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
