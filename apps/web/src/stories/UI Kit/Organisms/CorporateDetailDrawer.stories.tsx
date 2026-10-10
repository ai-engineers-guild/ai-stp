import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { CorporateDetailDrawer } from "@/components/organisms/corporate-people-ui";

import { withAppChrome } from "../../decorators";

/**
 * The one admin drawer: right-side sheet, title + description header, close
 * button in the top-right corner, focus returned to the trigger on close.
 * `wide` fits form-based editors (permission matrices, multi-selects);
 * the default width fits read/detail panels.
 */
const meta = {
  title: "UI Kit/Organisms/CorporateDetailDrawer",
  component: CorporateDetailDrawer,
  tags: ["autodocs"],
  decorators: [withAppChrome],
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof CorporateDetailDrawer>;

export default meta;
type Story = StoryObj<typeof meta>;

function DetailDemo({ wide = false }: { wide?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <Button onClick={() => setOpen(true)}>Open drawer</Button>
      <CorporateDetailDrawer
        open={open}
        onOpenChange={setOpen}
        title="Role details"
        description="Reference information and assignments for this role."
        wide={wide}
      >
        <div className="space-y-5">
          <div className="flex gap-3">
            <div>
              <h3 className="font-medium">Administrator</h3>
              <Badge variant="secondary" className="mt-1 font-sans">
                System role
              </Badge>
            </div>
          </div>
          <div>
            <h3 className="text-sm font-medium">Description</h3>
            <p className="text-muted-foreground mt-2 text-sm">
              Full access to every organization resource.
            </p>
          </div>
        </div>
      </CorporateDetailDrawer>
    </div>
  );
}

export const Default: Story = {
  render: () => <DetailDemo />,
};

export const Wide: Story = {
  render: () => <DetailDemo wide />,
};
