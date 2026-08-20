import type { Meta, StoryObj } from "@storybook/react";

import { Button } from "@/components/atoms/button";
import { StatePanel } from "@/components/molecules/state-panel";

const meta = {
  title: "UI Kit/Molecules/StatePanel",
  component: StatePanel,
  tags: ["autodocs"],
  args: {
    kind: "empty",
    title: "No catalog objects match this query.",
    description: "Try clearing filters or including experimental results.",
  },
} satisfies Meta<typeof StatePanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {};

export const Error: Story = {
  args: {
    kind: "error",
    title: "Something went wrong",
    description: "The service is temporarily unavailable. No data was fabricated.",
  },
};

export const Loading: Story = {
  args: {
    kind: "loading",
    title: "Loading…",
    description: "Fetching public catalog.",
  },
};

export const WithAction: Story = {
  args: {
    kind: "empty",
    title: "No results",
    description: "Adjust your query.",
    action: <Button size="sm">Clear filters</Button>,
  },
};
