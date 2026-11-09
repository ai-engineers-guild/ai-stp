import type { Meta, StoryObj } from "@storybook/react";
import { CorporateTechCategories } from "@/components/organisms/corporate-tech-categories";
import { authority, categories, technologies } from "@/mocks/technology-workspace-fixture";

const meta = {
  title: "UI Kit/Organisms/CorporateTechCategories",
  component: CorporateTechCategories,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
  args: {
    ...authority,
    capabilities: ["category.list", "category.read", "technology.list"],
    categories,
    technologies,
  },
} satisfies Meta<typeof CorporateTechCategories>;
export default meta;
type Story = StoryObj<typeof meta>;

export const ReadOnly: Story = {};
export const Dark: Story = { globals: { theme: "dark" } };
export const Empty: Story = { args: { categories: [] } };
export const Mobile: Story = {
  globals: { viewport: { value: "mobile1", isRotated: false } },
};
