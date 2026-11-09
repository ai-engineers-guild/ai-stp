import type { Meta, StoryObj } from "@storybook/react";

import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { EntityDetailHeader } from "@/components/organisms/entity-detail-header";
import { ObjectDetailFrame } from "@/components/organisms/object-detail-frame";
import { Icon } from "@/theme";
import { withAppChrome } from "@/stories/decorators";

function EntityDetailExample() {
  return (
    <article className="mx-auto max-w-7xl space-y-8">
      <EntityDetailHeader
        icon={
          <span className="flex size-20 items-center justify-center rounded-lg border border-border">
            <Icon name="technology" size="lg" />
          </span>
        }
        title="TypeScript"
        meta={<span className="text-sm text-muted-foreground">Technology · Adopt</span>}
        menu={
          <button type="button" aria-label="More actions">
            •••
          </button>
        }
      />
      <ObjectDetailFrame
        description={
          <section className="space-y-3">
            <h2 className="text-xl font-semibold">Description</h2>
            <p className="text-muted-foreground">Shared Markdown and media composition.</p>
          </section>
        }
        media={<div role="img" className="aspect-video rounded-lg bg-muted" aria-label="Media" />}
        main={
          <DetailAccordion title="Projects" summary="2" defaultOpen>
            <p>Web platform, Developer experience</p>
          </DetailAccordion>
        }
        rail={
          <section className="rounded-lg border border-border p-5">
            <p className="text-xs text-muted-foreground uppercase">Owner</p>
            <p className="mt-2 font-medium">Ada Lovelace</p>
          </section>
        }
      />
    </article>
  );
}

const meta = {
  title: "UI Kit/Organisms/EntityDetail",
  component: EntityDetailExample,
  decorators: [withAppChrome],
  tags: ["autodocs"],
} satisfies Meta<typeof EntityDetailExample>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Desktop: Story = {};

export const Mobile: Story = {
  parameters: { viewport: { defaultViewport: "mobile1" } },
};
