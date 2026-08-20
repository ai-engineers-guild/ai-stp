import type { Meta, StoryObj } from "@storybook/react";

import { spacing } from "@/theme";

function SpacingScale() {
  return (
    <div className="space-y-3">
      {Object.entries(spacing).map(([name, value]) => (
        <div key={name} className="flex items-center gap-4">
          <code className="text-muted-foreground w-16 font-mono text-xs">{name}</code>
          <div className="bg-primary h-4 rounded-sm" style={{ width: value }} />
          <span className="font-mono text-xs">{value}</span>
        </div>
      ))}
    </div>
  );
}

const meta = {
  title: "Foundations/Spacing",
  component: SpacingScale,
  tags: ["autodocs"],
} satisfies Meta<typeof SpacingScale>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Scale: Story = {};
