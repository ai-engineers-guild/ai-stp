import type { Meta, StoryObj } from "@storybook/react";

import { ConnectorSkeleton } from "@/components/molecules/connector-skeleton";

const meta = {
  title: "UI Kit/Molecules/ConnectorSkeleton",
  component: ConnectorSkeleton,
  tags: ["autodocs"],
  args: { label: "Loading connector" },
} satisfies Meta<typeof ConnectorSkeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
