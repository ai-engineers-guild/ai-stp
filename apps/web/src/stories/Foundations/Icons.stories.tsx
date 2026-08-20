import type { Meta, StoryObj } from "@storybook/react";

import { Icon, iconNames, type IconSize } from "@/theme";

function IconGrid({ size }: { size: IconSize }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-5">
      {iconNames.map((name) => (
        <div
          key={name}
          className="border-border flex flex-col items-center gap-2 rounded-lg border p-4"
        >
          <Icon name={name} size={size} className="text-foreground" />
          <code className="font-mono text-xs">{name}</code>
        </div>
      ))}
    </div>
  );
}

const meta = {
  title: "Foundations/Icons",
  component: IconGrid,
  args: { size: "md" as IconSize },
  argTypes: {
    size: { control: "select", options: ["sm", "md", "lg"] },
  },
  tags: ["autodocs"],
  parameters: {
    docs: {
      description: {
        component:
          "Icon registry (`src/theme/icons.tsx`). Add names there — do not import lucide in product pages.",
      },
    },
  },
} satisfies Meta<typeof IconGrid>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Registry: Story = {};
