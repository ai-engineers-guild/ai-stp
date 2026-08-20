import type { Meta, StoryObj } from "@storybook/react";

import { CatalogFilters } from "@/components/organisms/catalog-filters";
import { defaultCatalogQuery } from "@/lib/catalog-query-defaults";

const labels = {
  search: "Search",
  searchPlaceholder: "Search components and setups",
  searchHelp: "Structured query help",
  resourceLegend: "Catalog resource",
  components: "Components",
  setups: "Setups",
  resourceBoth: "Both",
  experimentalConsent: "Include experimental",
  tagFilter: "Tag",
  harnessFilter: "Harness",
  typeFilter: "Component type",
  supportTierFilter: "Support tier",
  supportStateFilter: "Support state",
  anyOption: "Any",
  applyFilters: "Apply filters",
  filtersButton: "Filters",
  resetAll: "Reset all",
  filterHelpTitle: "About filters",
  filterHelpBody: "Help text for trust and experimental lanes.",
  dismissFilter: "Remove filter",
  closeFilters: "Close",
  filterHelpLabel: "Help for filter",
  searchOptions: "Search options",
  authorFilter: "Author",
  verifiedOnly: "Only verified",
  serviceFilter: "External service",
  countryFilter: "Country",
  unspecifiedOption: "Not specified",
  sortBy: "Sort results",
  sortDirection: "Direction",
  sortRelevance: "Relevance",
  sortUpdated: "Recently updated",
  sortLikes: "Most liked",
  sortAscending: "Ascending",
  sortDescending: "Descending",
  viewLabel: "Result layout",
  cardsView: "Cards",
  listView: "List",
  refineButton: "Filters & sorting",
  queryCorrection: "Did you mean",
};

const meta = {
  title: "UI Kit/Organisms/CatalogFilters",
  component: CatalogFilters,
  tags: ["autodocs"],
  args: {
    query: defaultCatalogQuery("components"),
    labels,
  },
  parameters: {
    docs: {
      description: {
        component:
          "Compact catalog filters: search always on, extra filters in disclosure, multi-tag chips.",
      },
    },
  },
} satisfies Meta<typeof CatalogFilters>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ComponentsDefault: Story = {};

export const SetupsFiltered: Story = {
  args: {
    query: {
      ...defaultCatalogQuery("setups"),
      q: "python",
      tags: ["python"],
      harnessId: "claude-code",
    },
  },
};

export const ExperimentalOff: Story = {
  args: {
    query: {
      ...defaultCatalogQuery("components"),
      includeExperimental: false,
    },
  },
};

export const NarrowPhone: Story = {
  args: {
    query: {
      ...defaultCatalogQuery("components"),
      tags: ["python"],
      harnessIds: ["codex"],
    },
    intro: "Публичные компоненты и сетапы для конкретного харнесса.",
  },
  decorators: [
    (Story) => (
      <div className="w-[360px] max-w-full overflow-x-hidden">
        <Story />
      </div>
    ),
  ],
};
