import type { Meta, StoryObj } from "@storybook/react";

import { SwitchRow } from "@/components/molecules/switch-row";

const meta = {
  title: "UI Kit/Molecules/SwitchRow",
  component: SwitchRow,
  tags: ["autodocs"],
  args: {
    id: "story-switch",
    name: "story_switch",
    label: "Runtime usage collection",
    value: true,
    disabled: false,
  },
} satisfies Meta<typeof SwitchRow>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Plain: Story = {};

export const WithDescription: Story = {
  args: {
    description: "Collect anonymized runtime and usage data from installations.",
  },
};

export const WithStatus: Story = {
  args: {
    description: "Control periodic installation heartbeat reporting.",
    status: {
      on: "Enabled",
      off: "Disabled",
      onHint: "Installation heartbeat reporting is active.",
      offHint: "Heartbeat reporting is paused.",
    },
  },
};

export const CardHeader: Story = {
  args: {
    icon: "activity",
    label: "Device heartbeat",
    description: "Control periodic installation heartbeat reporting.",
    status: {
      on: "Enabled",
      off: "Disabled",
      onHint: "Installation heartbeat reporting is active.",
      offHint: "Heartbeat reporting is paused.",
    },
  },
};

export const Disabled: Story = {
  args: { disabled: true, status: { on: "Enabled", off: "Disabled" } },
};
