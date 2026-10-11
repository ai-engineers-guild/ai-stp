import type { Meta, StoryObj } from "@storybook/react";

import { ClipboardIconButton } from "@/components/molecules/clipboard-icon-button";

const meta = {
  title: "UI Kit/Molecules/ClipboardIconButton",
  component: ClipboardIconButton,
  tags: ["autodocs"],
  args: {
    value: "npx ai-stp install",
    label: "Copy command",
    copiedLabel: "Copied",
  },
} satisfies Meta<typeof ClipboardIconButton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const IconOnly: Story = {};

export const Labeled: Story = {
  args: {
    variant: "secondary",
    children: "Copy command",
  },
};
