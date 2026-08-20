import type { Meta, StoryObj } from "@storybook/react";

import { fontFamilyMono, fontFamilySans, fontSizes, fontWeights } from "@/theme";

function TypographyScale() {
  return (
    <div className="space-y-8">
      <section className="space-y-2">
        <h2 className="text-lg font-medium">Font families</h2>
        <p className="text-base" style={{ fontFamily: fontFamilySans }}>
          Sans — The quick brown fox jumps over the lazy dog.
        </p>
        <p className="text-base" style={{ fontFamily: fontFamilyMono }}>
          Mono — component_01JQZK7B · v1.2
        </p>
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Sizes</h2>
        {Object.entries(fontSizes).map(([name, value]) => (
          <p key={name} style={{ fontSize: value }} className="leading-snug">
            <span className="text-muted-foreground mr-2 font-mono text-xs">
              {name} ({value})
            </span>
            Build harness setups without a second source of truth.
          </p>
        ))}
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-medium">Weights</h2>
        {Object.entries(fontWeights).map(([name, value]) => (
          <p key={name} style={{ fontWeight: value }}>
            {name} ({value}) — ai_stp catalog
          </p>
        ))}
      </section>
    </div>
  );
}

const meta = {
  title: "Foundations/Typography",
  component: TypographyScale,
  tags: ["autodocs"],
} satisfies Meta<typeof TypographyScale>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Scale: Story = {};
