import type { Meta, StoryObj } from "@storybook/react";

import { radii } from "@/theme";

function RadiusScale() {
  return (
    <div className="flex flex-wrap gap-6">
      {Object.entries(radii).map(([name, value]) => (
        <div key={name} className="flex flex-col items-center gap-2">
          <div
            className="border-border bg-secondary h-20 w-20 border-2"
            style={{ borderRadius: value }}
          />
          <code className="font-mono text-xs">
            {name} · {value}
          </code>
        </div>
      ))}
    </div>
  );
}

const meta = {
  title: "Foundations/Radius",
  component: RadiusScale,
  tags: ["autodocs"],
} satisfies Meta<typeof RadiusScale>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Scale: Story = {};
