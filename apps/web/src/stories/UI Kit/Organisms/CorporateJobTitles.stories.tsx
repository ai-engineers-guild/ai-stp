import type { Meta, StoryObj } from "@storybook/react";
import { CorporateJobTitles } from "@/components/organisms/corporate-job-titles";
import { authority, jobTitles } from "@/mocks/technology-workspace-fixture";

const meta = {
  title: "UI Kit/Organisms/CorporateJobTitles",
  component: CorporateJobTitles,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
  args: {
    ...authority,
    capabilities: ["job_title.list", "member.list"],
    jobTitles,
    members: [],
  },
} satisfies Meta<typeof CorporateJobTitles>;
export default meta;
type Story = StoryObj<typeof meta>;

export const ReadOnly: Story = {};
export const Dark: Story = { globals: { theme: "dark" } };
export const Empty: Story = { args: { jobTitles: [] } };
export const Mobile: Story = {
  globals: { viewport: { value: "mobile1", isRotated: false } },
};
