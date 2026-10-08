import * as React from "react";

import { cn } from "@/lib/cn";

/**
 * Select — ai_stp design system (docs/product/DESIGN.md).
 * The single owner of native `<select>` styling: tokens only, 44px hit area,
 * `rounded-sm` control radius, shared focus ring with Input.
 */
export const selectClass =
  "border-input bg-background focus-visible:ring-ring h-11 w-full min-w-0 rounded-sm border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none";

export type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement>;

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, ...props }, ref) => (
    <select ref={ref} data-ui="ui-select" className={cn(selectClass, className)} {...props} />
  ),
);
Select.displayName = "Select";
