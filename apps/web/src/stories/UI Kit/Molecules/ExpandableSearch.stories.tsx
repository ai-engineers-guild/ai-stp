import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";
import { NextIntlClientProvider } from "next-intl";
import en from "../../../../messages/en.json";

import { ExpandableSearch } from "@/components/molecules/expandable-search";

const meta = {
  title: "UI Kit/Molecules/ExpandableSearch",
  component: ExpandableSearch,
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <NextIntlClientProvider locale="en" messages={en}>
        <div className="bg-background text-foreground min-h-dvh p-5">
          <Story />
        </div>
      </NextIntlClientProvider>
    ),
  ],
  render: () => {
    const [query, setQuery] = useState("");
    return (
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-3">
        <ExpandableSearch
          id="story-expandable-search"
          value={query}
          onChange={setQuery}
          label={en.hub.openSearch}
          fieldLabel={en.hub.search}
          placeholder={en.hub.search}
        />
      </div>
    );
  },
} satisfies Meta<typeof ExpandableSearch>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
