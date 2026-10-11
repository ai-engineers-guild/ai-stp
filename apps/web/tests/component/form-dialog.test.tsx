import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { Button } from "@/components/atoms/button";
import { FormDialog } from "@/components/molecules/form-dialog";

function Demo({ onSubmit = vi.fn() }: { onSubmit?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        onClick={() => {
          setOpen(true);
        }}
      >
        New
      </Button>
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title="Create role"
        description="Roles bundle permissions."
        closeLabel="Close"
        cancelLabel="Cancel"
        submitLabel="Save"
        onSubmit={() => {
          onSubmit();
          setOpen(false);
        }}
      >
        <input name="name" aria-label="Name" />
      </FormDialog>
    </>
  );
}

it("opens centered, submits the form, and closes via cancel, close, and Escape", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  render(<Demo onSubmit={onSubmit} />);

  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "New" }));
  const dialog = screen.getByRole("dialog", { name: "Create role" });
  expect(dialog).toBeVisible();

  await user.type(screen.getByRole("textbox", { name: "Name" }), "editor");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(onSubmit).toHaveBeenCalledOnce();

  await user.click(screen.getByRole("button", { name: "New" }));
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "New" }));
  await user.click(screen.getByRole("button", { name: "Close" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "New" }));
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("shows the inline error and blocks closing while busy", async () => {
  const user = userEvent.setup();
  const onOpenChange = vi.fn();
  render(
    <FormDialog
      open
      onOpenChange={onOpenChange}
      title="Create role"
      closeLabel="Close"
      cancelLabel="Cancel"
      submitLabel="Save"
      busy
      busyLabel="Saving…"
      error="Name is required"
      onSubmit={vi.fn()}
    >
      <input name="name" aria-label="Name" />
    </FormDialog>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Name is required");
  expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
  await user.keyboard("{Escape}");
  expect(onOpenChange).not.toHaveBeenCalled();
});
