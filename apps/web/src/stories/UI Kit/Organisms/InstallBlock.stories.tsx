import type { Meta, StoryObj } from "@storybook/react";

import { InstallBlock } from "@/components/organisms/install-block";

const meta = {
  title: "UI Kit/Organisms/InstallBlock",
  component: InstallBlock,
  tags: ["autodocs"],
  parameters: {
    docs: {
      description: {
        component: "Landing install command with copy action and prerequisites list.",
      },
    },
  },
} satisfies Meta<typeof InstallBlock>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Mobile360: Story = {
  parameters: { viewport: { defaultViewport: "mobile1" } },
};

export const Mobile430: Story = {
  parameters: {
    viewport: { defaultViewport: "mobile2" },
    chromatic: { viewports: [360, 430] },
  },
};
