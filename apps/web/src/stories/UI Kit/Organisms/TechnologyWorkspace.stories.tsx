import type { Meta, StoryObj } from "@storybook/react";
import { NextIntlClientProvider } from "next-intl";
import ru from "../../../../messages/ru.json";
import { TechnologyScanFindings } from "@/components/organisms/technology-scan-findings";
import { TechnologyLandscapeResults } from "@/components/organisms/technology-landscape-results";
import { TechnologyScanJournal } from "@/components/organisms/technology-scan-journal";
import {
  authority,
  scan,
  projects,
  technologies,
  categories,
  areas,
  landscape,
} from "@/mocks/technology-workspace-fixture";
const meta = {
  title: "UI Kit/Organisms/TechnologyWorkspace",
  component: TechnologyScanFindings,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
  decorators: [
    (Story) => (
      <NextIntlClientProvider locale="ru" messages={ru}>
        <div className="technology-workspace bg-background text-foreground min-h-dvh p-5">
          <Story />
        </div>
      </NextIntlClientProvider>
    ),
  ],
  args: { ...authority, scans: [scan], projects, technologies, categories, areas, canUpdate: true },
} satisfies Meta<typeof TechnologyScanFindings>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Scan: Story = {};
export const Mapping: Story = { args: { mode: "mapping" } };
export const ReadOnly: Story = { args: { canUpdate: false } };
export const Empty: Story = { args: { scans: [] } };
export const Dark: Story = { globals: { theme: "dark" } };
export const Map: Story = {
  render: () => (
    <TechnologyLandscapeResults
      landscape={landscape}
      filters={{ view: "grouped" }}
      categories={categories}
      areas={areas}
    />
  ),
};
export const Table: Story = {
  render: () => (
    <TechnologyLandscapeResults
      landscape={landscape}
      filters={{ view: "table" }}
      categories={categories}
      areas={areas}
    />
  ),
};
export const Journal: Story = {
  render: () => <TechnologyScanJournal items={[scan]} projects={projects} />,
};
