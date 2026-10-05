import type { Meta, StoryObj } from "@storybook/react";

import { InfoNote } from "@/components/molecules/info-note";

const meta = {
  title: "UI Kit/Molecules/InfoNote",
  component: InfoNote,
  tags: ["autodocs"],
  args: {
    children:
      "Only technical usage data is collected. No source code, content or personal data is collected.",
  },
} satisfies Meta<typeof InfoNote>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const CustomIcon: Story = {
  args: { icon: "lock", children: "Existing members retain their access." },
};
