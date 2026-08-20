import * as React from "react";

import { cn } from "@/lib/cn";
import { UI } from "@/lib/ui-selectors";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

/** Multiline control — matches Input (radius sm, token border/focus). */
export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        data-ui={UI.primitive.textarea}
        className={cn(
          [
            "border-input bg-background flex min-h-[80px] w-full rounded-sm border px-3 py-2",
            "text-foreground text-sm",
            "ring-offset-background",
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
Textarea.displayName = "Textarea";
