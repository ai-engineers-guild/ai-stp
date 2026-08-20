import type { Meta, StoryObj } from "@storybook/react";

import { Skeleton } from "@/components/atoms/skeleton";

const meta = {
  title: "UI Kit/Atoms/Skeleton",
  component: Skeleton,
  tags: ["autodocs"],
} satisfies Meta<typeof Skeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const CardPlaceholder: Story = {
  render: () => (
    <div className="border-border bg-card w-80 space-y-3 rounded-lg border p-4 shadow-sm">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-6 w-2/3" />
      <Skeleton className="h-16 w-full" />
      <div className="flex gap-2">
        <Skeleton className="h-5 w-16 rounded-md" />
        <Skeleton className="h-5 w-20 rounded-md" />
      </div>
    </div>
  ),
};
