import type { Meta, StoryObj } from "@storybook/react";

import { CatalogResults } from "@/components/organisms/catalog-results";
import {
  componentSummaryFixture,
  setupSummaryFixture,
  ALL_COMPONENT_SUMMARIES,
  ALL_SETUP_SUMMARIES,
} from "@/mocks/fixtures/catalog";
import type { ComponentSummary, SetupSummary } from "@/lib/api/generated/types.gen";

const labels = {
  authoritative: "Authoritative",
  experimental: "Experimental",
  experimentalNote:
    "Authoritative and experimental lanes are merged here. Author verification is not a content-safety proof.",
  emptyAuthoritative: "No authoritative results",
  emptyExperimental: "No experimental results",
  emptyAll: "No catalog objects match this query.",
  resultsHeading: "Components",
  nextPage: "Next page",
  version: "Version",
  harness: "Harness",
  type: "Type",
  tags: "Tags",
  purpose: "Purpose",
  targetRole: "Role",
  authorVerified: "Author verified",
  componentVerified: "Component verified",
  yes: "yes",
  no: "no",
  publisher: "Publisher",
  componentKind: "Component",
  setupKind: "Setup",
};

const meta = {
  title: "UI Kit/Organisms/CatalogResults",
  component: CatalogResults,
  tags: ["autodocs"],
} satisfies Meta<typeof CatalogResults>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ComponentsGrid: Story = {
  args: {
    kind: "components",
    items: [],
    experimental: ALL_COMPONENT_SUMMARIES.slice(0, 6) as ComponentSummary[],
    nextCursor: "cursor_demo",
    showExperimental: true,
    basePath: "/catalog",
    query: { resource: "components", include_experimental: "1", page_size: "25" },
    labels: { ...labels, resultsHeading: "Components" },
  },
};

export const SetupsList: Story = {
  args: {
    kind: "setups",
    items: [],
    experimental: ALL_SETUP_SUMMARIES.slice(0, 4) as SetupSummary[],
    nextCursor: null,
    showExperimental: true,
    basePath: "/catalog",
    query: { resource: "setups", include_experimental: "1", page_size: "25" },
    labels: { ...labels, resultsHeading: "Setups" },
  },
};

export const Empty: Story = {
  args: {
    kind: "components",
    items: [],
    experimental: [],
    nextCursor: null,
    showExperimental: true,
    basePath: "/catalog",
    query: { resource: "components" },
    labels,
  },
};

export const NarrowPhone: Story = {
  args: {
    kind: "mixed",
    items: ALL_SETUP_SUMMARIES.slice(0, 1) as SetupSummary[],
    experimental: ALL_COMPONENT_SUMMARIES.slice(0, 2) as ComponentSummary[],
    nextCursor: null,
    showExperimental: true,
    view: "list",
    basePath: "/catalog",
    query: { resource: "all" },
    labels: { ...labels, resultsHeading: "Все результаты" },
  },
  decorators: [
    (Story) => (
      <div className="w-[360px] max-w-full overflow-x-hidden">
        <Story />
      </div>
    ),
  ],
};

export const SingleCards: Story = {
  args: {
    kind: "components",
    items: [
      {
        ...componentSummaryFixture,
        latest_trust: {
          trust_lane: "authoritative",
          author_verified: true,
          component_verified: true,
        },
      } as ComponentSummary,
    ],
    experimental: [setupSummaryFixture as unknown as ComponentSummary].slice(0, 0),
    nextCursor: null,
    showExperimental: true,
    basePath: "/catalog",
    query: {},
    labels,
  },
};
