import * as React from "react";

import { cn } from "@/lib/cn";
import { UI } from "@/lib/ui-selectors";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

/** Form control — radius sm (4px), 1px border, token colors only. */
export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        data-ui={UI.primitive.input}
        type={type}
        className={cn(
          [
            "border-input bg-background flex h-10 w-full rounded-sm border px-3 py-2",
            "text-foreground text-sm",
            "ring-offset-background",
            "file:border-0 file:bg-transparent file:text-sm file:font-medium",
            "placeholder:text-muted-foreground",
            "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none",
            "disabled:cursor-not-allowed disabled:opacity-50",
            "transition-colors duration-[var(--duration-fast)]",
          ].join(" "),
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";
