import type { Meta, StoryObj } from "@storybook/react";

import { COLOR_ROLES, colorChannels, type ColorRole } from "@/theme";

function ColorSwatch({ role }: { role: ColorRole }) {
  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-border shadow-sm">
      <div
        className="h-16 w-full"
        style={{ backgroundColor: `hsl(${colorChannels(role, "light")})` }}
      />
      <div className="space-y-1 p-3">
        <p className="text-sm font-medium">{role}</p>
        <p className="font-mono text-xs text-muted-foreground">
          light: {colorChannels(role, "light")}
        </p>
        <p className="font-mono text-xs text-muted-foreground">
          dark: {colorChannels(role, "dark")}
        </p>
        <p className="text-xs">
          Utility: <code className="rounded bg-muted px-1">bg-{role}</code> /{" "}
          <code className="rounded bg-muted px-1">text-{role}</code>
        </p>
      </div>
    </div>
  );
}

function ColorsGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {COLOR_ROLES.map((role) => (
        <ColorSwatch key={role} role={role} />
      ))}
    </div>
  );
}

const meta = {
  title: "Foundations/Colors",
  component: ColorsGrid,
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Semantic color roles from tokens.json. Product code must use these roles, never raw hex.",
      },
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ColorsGrid>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Palette: Story = {};
