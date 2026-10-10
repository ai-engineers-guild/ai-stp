import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { FormDialog } from "@/components/molecules/form-dialog";

/**
 * The one centered create/edit modal for administration forms: title +
 * description, fields, then Cancel + primary submit. Domain dialogs supply
 * only fields and the submit handler; close, focus, and the footer live here.
 * `wide` fits multi-column or permission-matrix forms.
 */
const meta = {
  title: "UI Kit/Molecules/FormDialog",
  component: FormDialog,
  tags: ["autodocs"],
} satisfies Meta<typeof FormDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

function FormDialogDemo({ busy = false, error = null, wide = false }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <Button onClick={() => setOpen(true)}>Create job title</Button>
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title="Create job title"
        description="Job titles group members for reporting and assignment."
        closeLabel="Close"
        cancelLabel="Cancel"
        submitLabel="Save"
        busyLabel="Saving…"
        busy={busy}
        wide={wide}
        error={error}
        onSubmit={() => setOpen(false)}
      >
        <div className="space-y-1.5">
          <Label htmlFor="demo-title-name">Name</Label>
          <Input id="demo-title-name" name="name" required />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="demo-title-description">Description</Label>
          <Input id="demo-title-description" name="description" />
        </div>
      </FormDialog>
    </div>
  );
}

export const Default: Story = {
  render: () => <FormDialogDemo />,
};

export const Wide: Story = {
  render: () => <FormDialogDemo wide />,
};

export const Saving: Story = {
  render: () => <FormDialogDemo busy />,
};

export const WithError: Story = {
  render: () => <FormDialogDemo error="Name is already used by another job title." />,
};
