import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";

import { cn } from "@/lib/cn";
import { UI } from "@/lib/ui-selectors";

/**
 * Badge — mono chips, radius md (6px). High-density meta for trust / harness / tags.
 */
const badgeVariants = cva(
  [
    "inline-flex items-center",
    "rounded-md border border-border",
    "px-2 py-0.5",
    "font-mono text-[11px] font-medium tracking-wide",
    "transition-colors duration-[var(--duration-fast)]",
  ].join(" "),
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "bg-transparent text-foreground",
        success: "border-transparent bg-success text-success-foreground",
        warning: "border-transparent bg-warning text-warning-foreground",
        destructive: "border-transparent bg-destructive text-destructive-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export type BadgeProps = React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof badgeVariants>;

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div
      data-ui={UI.primitive.badge}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}

export { badgeVariants };
