import type { Meta, StoryObj } from "@storybook/react";

import { PagePager } from "@/components/molecules/page-pager";

const meta = {
  title: "UI Kit/Molecules/PagePager",
  component: PagePager,
  tags: ["autodocs"],
} satisfies Meta<typeof PagePager>;

export default meta;
type Story = StoryObj<typeof meta>;

const controls = {
  previous: "Previous page",
  next: "Next page",
  page: (value: number) => `Page ${value}`,
};

export const Links: Story = {
  args: {
    label: "Pagination",
    page: 4,
    totalPages: 12,
    controls,
    hrefFor: (page: number) => `/catalog?page=${page}`,
  },
};

export const Buttons: Story = {
  args: {
    label: "Pagination",
    page: 2,
    totalPages: 8,
    controls,
    onPage: () => {},
    summary: <span className="text-muted-foreground text-sm">Showing 11–20 of 75</span>,
  },
};

export const NumbersOnly: Story = {
  args: {
    label: "Pagination",
    page: 1,
    totalPages: 5,
    hrefFor: (page: number) => `/catalog?page=${page}`,
  },
};
