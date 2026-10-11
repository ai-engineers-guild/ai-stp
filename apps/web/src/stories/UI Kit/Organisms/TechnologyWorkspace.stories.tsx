import type { Meta, StoryObj } from "@storybook/react";
import { NextIntlClientProvider } from "next-intl";
import ru from "../../../../messages/ru.json";
import { TechnologyScanFindings } from "@/components/organisms/technology-scan-findings";
import { TechnologyFilterToolbar } from "@/components/organisms/technology-filter-toolbar";
import { TechnologyLandscapeResults } from "@/components/organisms/technology-landscape-results";
import { TechnologyScanJournal } from "@/components/organisms/technology-scan-journal";
import { TaxonomyDirectory } from "@/components/organisms/taxonomy-directory";
import { JobTitleDirectory } from "@/components/organisms/job-title-directory";
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
      filters={{}}
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
export const Taxonomy: Story = {
  render: () => (
    <TaxonomyDirectory
      kind="category"
      items={categories}
      areas={areas}
      authority={authority}
      canCreate
      canUpdate
      canRemove
      detailBase="/corporate/admin/technology-categories"
    />
  ),
};
export const TaxonomyAreas: Story = {
  render: () => (
    <TaxonomyDirectory
      kind="area"
      items={areas}
      areas={areas}
      categories={categories}
      authority={authority}
      canCreate
      canUpdate
      canRemove
    />
  ),
};
export const JobTitles: Story = {
  render: () => (
    <JobTitleDirectory
      csrfToken="storybook"
      organizationId={authority.organizationId}
      authorizationRevision={authority.authorizationRevision}
      permissions={["job_title.list", "job_title.create", "job_title.update"]}
      jobTitles={[
        {
          schema_version: 1,
          job_title_id: "job_title_01JQZK7B8N4M6P2R9T5V0X3Y11",
          organization_id: authority.organizationId,
          name: "Platform engineer",
          normalized_name: "platform engineer",
          description: "Builds and operates the internal developer platform.",
          state: "current",
          revision: 1,
        },
        {
          schema_version: 1,
          job_title_id: "job_title_01JQZK7B8N4M6P2R9T5V0X3Y22",
          organization_id: authority.organizationId,
          name: "Legacy maintainer",
          normalized_name: "legacy maintainer",
          description: "Kept the retired services alive.",
          state: "retired",
          revision: 2,
        },
      ]}
    />
  ),
};
export const Journal: Story = {
  render: () => <TechnologyScanJournal items={[scan]} projects={projects} />,
};
export const FilterToolbar: Story = {
  render: () => (
    <TechnologyFilterToolbar
      search=""
      searchPlaceholder="Search findings, files, technologies…"
      onSearchChange={() => {}}
      facets={[
        {
          kind: "options",
          key: "project",
          label: "Project",
          options: projects.map((p) => ({ value: p.project_id, label: p.name })),
        },
        {
          kind: "options",
          key: "status",
          label: "Status",
          options: [
            { value: "open", label: "Open" },
            { value: "resolved", label: "Resolved" },
          ],
        },
        { kind: "date", key: "date", label: "Starting from date" },
        { kind: "flag", key: "pending", label: "Only findings needing review" },
      ]}
      values={{ project: [], status: ["open"], date: "", pending: true }}
      onApply={() => {}}
      onReset={() => {}}
    />
  ),
};
