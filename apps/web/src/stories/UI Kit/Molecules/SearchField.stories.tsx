import type { Meta, StoryObj } from "@storybook/react";

import { SearchField } from "@/components/molecules/search-field";

const meta = {
  title: "UI Kit/Molecules/SearchField",
  component: SearchField,
  tags: ["autodocs"],
  args: {
    id: "catalog-search",
    label: "Search",
    placeholder: "Search components and setups",
    submitLabel: "Search",
    defaultValue: "",
  },
} satisfies Meta<typeof SearchField>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithQuery: Story = {
  args: { defaultValue: "python" },
};
