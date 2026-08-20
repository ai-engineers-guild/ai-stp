import type { Meta, StoryObj } from "@storybook/react";

import { ObjectCard } from "@/components/organisms/object-card";
import { componentSummaryFixture, setupSummaryFixture } from "@/mocks/fixtures/catalog";
import type { ComponentSummary, SetupSummary } from "@/lib/api/generated/types.gen";

const labels = {
  version: "Version",
  harness: "Harness",
  type: "Type",
  tags: "Tags",
  authorVerified: "Author verified",
  componentVerified: "Component verified",
  yes: "yes",
  no: "no",
  purpose: "Purpose",
  targetRole: "Role",
  componentKind: "Component",
  setupKind: "Setup",
};

const meta = {
  title: "UI Kit/Organisms/ObjectCard",
  component: ObjectCard,
  tags: ["autodocs"],
  parameters: {
    docs: {
      description: {
        component:
          "Catalog card. Components use primary accent; setups use success accent and purpose/role meta.",
      },
    },
  },
} satisfies Meta<typeof ObjectCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Component: Story = {
  args: {
    kind: "component",
    item: componentSummaryFixture as ComponentSummary,
    href: "/catalog/components/x",
    labels,
  },
};

export const Setup: Story = {
  args: {
    kind: "setup",
    item: setupSummaryFixture as SetupSummary,
    href: "/catalog/setups/x",
    labels,
  },
};

export const AuthoritativeComponent: Story = {
  args: {
    kind: "component",
    item: {
      ...componentSummaryFixture,
      latest_trust: {
        trust_lane: "authoritative",
        author_verified: true,
        component_verified: true,
      },
    } as ComponentSummary,
    href: "/catalog/components/x",
    labels,
  },
};

export const NarrowList: Story = {
  args: {
    kind: "component",
    item: {
      ...componentSummaryFixture,
      latest_name: "Очень длинное имя компонента для узкой колонки каталога",
    } as ComponentSummary,
    href: "/catalog/components/x",
    labels,
    view: "list",
  },
  decorators: [
    (Story) => (
      <div className="w-[360px] max-w-full overflow-x-hidden">
        <Story />
      </div>
    ),
  ],
};

export const SideBySide: Story = {
  args: {
    kind: "component",
    item: componentSummaryFixture as ComponentSummary,
    href: "/c",
    labels,
  },
  render: () => (
    <div className="grid gap-4 md:grid-cols-2">
      <ObjectCard
        kind="component"
        item={componentSummaryFixture as ComponentSummary}
        href="/c"
        labels={labels}
      />
      <ObjectCard
        kind="setup"
        item={setupSummaryFixture as SetupSummary}
        href="/s"
        labels={labels}
      />
    </div>
  ),
};
