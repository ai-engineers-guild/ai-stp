"use client";

import { useState } from "react";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Icon } from "@/theme";

/** Standard toolbar search: an icon button that expands into a full-width field. */
export function ExpandableSearch({
  value,
  onChange,
  onSubmit,
  label,
  fieldLabel,
  placeholder,
  id = "expandable-search",
}: {
  value: string;
  onChange: (value: string) => void;
  /** When provided, the field icon becomes a submit control and Enter commits. */
  onSubmit?: (() => void) | undefined;
  /** Toggle button label, e.g. hub.openSearch. */
  label: string;
  /** Visible label above the expanded field; falls back to `label`. */
  fieldLabel?: string | undefined;
  placeholder?: string | undefined;
  id?: string | undefined;
}) {
  const [open, setOpen] = useState(Boolean(value));
  return (
    <>
      <Button
        type="button"
        variant={open ? "default" : "outline"}
        size="icon"
        aria-expanded={open}
        aria-label={label}
        title={label}
        onClick={() => {
          setOpen((previous) => !previous);
        }}
      >
        <Icon name="search" size="sm" />
      </Button>
      {open ? (
        <form
          className="border-border bg-card basis-full rounded-lg border p-3"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit?.();
          }}
        >
          <label htmlFor={id} className="space-y-1.5 text-sm font-medium">
            <span>{fieldLabel ?? label}</span>
            <span className="relative block">
              {onSubmit ? (
                <Button
                  type="submit"
                  size="icon"
                  variant="ghost"
                  className="absolute top-1/2 left-1 size-9 -translate-y-1/2"
                  aria-label={fieldLabel ?? label}
                >
                  <Icon name="search" size="sm" />
                </Button>
              ) : (
                <Icon
                  name="search"
                  size="sm"
                  className="text-muted-foreground absolute top-1/2 left-3 -translate-y-1/2"
                />
              )}
              <Input
                id={id}
                value={value}
                onChange={(event) => {
                  onChange(event.target.value);
                }}
                placeholder={placeholder}
                className="h-11 pl-10"
              />
            </span>
          </label>
        </form>
      ) : null}
    </>
  );
}
