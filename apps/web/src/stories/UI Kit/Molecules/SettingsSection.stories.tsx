import type { Meta, StoryObj } from "@storybook/react";

import { Badge } from "@/components/atoms/badge";
import { SettingsSection } from "@/components/molecules/settings-section";
import { SwitchRow } from "@/components/molecules/switch-row";

const meta = {
  title: "UI Kit/Molecules/SettingsSection",
  component: SettingsSection,
  tags: ["autodocs"],
  args: {
    icon: "activity",
    title: "Device heartbeat",
    description: "Control periodic installation heartbeat reporting.",
    children: <p className="text-muted-foreground text-sm">Section body</p>,
  },
} satisfies Meta<typeof SettingsSection>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithAside: Story = {
  args: {
    aside: <Badge variant="success">Enabled</Badge>,
  },
};

export const CompositeHeader: Story = {
  args: {
    icon: undefined,
    title: undefined,
    description: undefined,
    header: (
      <SwitchRow
        id="story-header-switch"
        name="story_header_switch"
        icon="activity"
        label="Device heartbeat"
        description="Control periodic installation heartbeat reporting."
        value
        disabled={false}
        status={{
          on: "Enabled",
          off: "Disabled",
          onHint: "Installation heartbeat reporting is active.",
          offHint: "Heartbeat reporting is paused.",
        }}
      />
    ),
  },
};
