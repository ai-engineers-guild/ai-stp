"use client";

import { useState } from "react";

import { cn } from "@/lib/cn";
import { UI } from "@/lib/ui-selectors";

/** Boolean control that still submits "true"/"false" through a hidden input,
 * so server forms keep their plain string contract. */
export function Switch({
  id,
  name,
  defaultChecked,
  disabled,
  "aria-label": ariaLabel,
}: {
  id?: string;
  name: string;
  defaultChecked: boolean;
  disabled?: boolean;
  "aria-label"?: string;
}) {
  const [on, setOn] = useState(defaultChecked);
  return (
    <>
      <input type="hidden" name={name} value={on ? "true" : "false"} />
      <span className="relative inline-flex shrink-0">
        <input
          id={id}
          type="checkbox"
          checked={on}
          disabled={disabled}
          aria-label={ariaLabel}
          onChange={(event) => {
            setOn(event.target.checked);
          }}
          className="peer sr-only"
        />
        <span
          data-ui={UI.primitive.switch}
          aria-hidden="true"
          className={cn(
            "bg-muted h-6 w-11 rounded-full transition-colors duration-[var(--duration-fast)]",
            "peer-checked:bg-primary peer-focus-visible:ring-ring peer-focus-visible:ring-2",
            "peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
          )}
        />
        <span
          aria-hidden="true"
          className="bg-background absolute top-0.5 left-0.5 h-5 w-5 rounded-full shadow-sm transition-transform duration-[var(--duration-fast)] peer-checked:translate-x-5"
        />
      </span>
    </>
  );
}
