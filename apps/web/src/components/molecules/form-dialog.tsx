"use client";

import type { FormEvent, ReactNode } from "react";

import { Button } from "@/components/atoms/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/atoms/dialog";

/**
 * Uniform centered create/edit modal: title, optional description, the caller's
 * fields, then Cancel + primary submit with a busy state. Domain dialogs only
 * own their fields and the submit handler — chrome, focus, and footer live here.
 */
export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  closeLabel,
  cancelLabel,
  submitLabel,
  busyLabel,
  busy = false,
  submitDisabled = false,
  submitVariant = "default",
  wide = false,
  error = null,
  onSubmit,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string | undefined;
  closeLabel: string;
  cancelLabel: string;
  submitLabel: string;
  busyLabel?: string | undefined;
  busy?: boolean;
  submitDisabled?: boolean;
  /** `destructive` for irreversible confirms (delete, revoke). */
  submitVariant?: "default" | "destructive";
  /** Wider body for permission matrices and multi-column forms. */
  wide?: boolean;
  error?: string | null;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  children?: ReactNode;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!busy) onOpenChange(next);
      }}
    >
      <DialogContent
        closeLabel={closeLabel}
        className={`max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] overflow-y-auto ${
          wide ? "max-w-3xl" : ""
        }`}
      >
        <DialogTitle>{title}</DialogTitle>
        {description ? <DialogDescription>{description}</DialogDescription> : null}
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit(event);
          }}
        >
          {children}
          {error ? (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          ) : null}
          <DialogFooter className="gap-2 sm:space-x-0">
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => {
                onOpenChange(false);
              }}
            >
              {cancelLabel}
            </Button>
            <Button
              type="submit"
              variant={submitVariant === "destructive" ? "destructive" : "default"}
              disabled={busy || submitDisabled}
            >
              {busy ? (busyLabel ?? submitLabel) : submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
