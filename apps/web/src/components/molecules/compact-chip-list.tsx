"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

import { Badge, badgeVariants } from "@/components/atoms/badge";
import { cn } from "@/lib/cn";

const VISIBLE_LIMIT = 3;

/** Keep dense compatibility metadata readable without hiding the full value set. */
export function CompactChipList({
  values,
  label,
  variant = "outline",
  className,
}: {
  values: readonly string[];
  label: string;
  variant?: "default" | "secondary" | "outline" | "success" | "warning" | "destructive";
  className?: string;
}) {
  const unique = [...new Set(values)].filter(Boolean);
  if (unique.length === 0) return null;
  const visible = unique.slice(0, VISIBLE_LIMIT);
  const hidden = unique.slice(VISIBLE_LIMIT);

  return (
    <div className={cn("flex min-w-0 flex-wrap items-center gap-1", className)} aria-label={label}>
      {visible.map((value) => (
        <Badge key={value} variant={variant}>
          {value}
        </Badge>
      ))}
      {hidden.length ? (
        <span className="relative z-30 shrink-0">
          <DropdownMenu.Root modal={false}>
            <DropdownMenu.Trigger asChild>
              <button
                type="button"
                className={cn(
                  badgeVariants({ variant }),
                  "focus-visible:ring-ring relative cursor-pointer focus-visible:ring-2 focus-visible:outline-none",
                )}
                aria-label={`${label}: ${unique.join(", ")}`}
              >
                +{hidden.length}
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                side="top"
                align="start"
                sideOffset={8}
                collisionPadding={12}
                className="border-border bg-popover text-popover-foreground z-[80] w-max max-w-[min(18rem,calc(100vw-2rem))] rounded-lg border p-2 shadow-md"
              >
                <p className="text-muted-foreground mb-1 text-xs font-medium">{label}</p>
                <div className="flex flex-wrap gap-1">
                  {unique.map((value) => (
                    <Badge key={value} variant={variant}>
                      {value}
                    </Badge>
                  ))}
                </div>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </span>
      ) : null}
    </div>
  );
}
