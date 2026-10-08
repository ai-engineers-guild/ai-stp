"use client";

import { Badge, badgeVariants } from "@/components/atoms/badge";
import { cn } from "@/lib/cn";
import { Link } from "@/lib/i18n/navigation";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/atoms/menu";

const VISIBLE_LIMIT = 3;

/** Keep dense compatibility metadata readable without hiding the full value set. */
export function CompactChipList({
  values,
  label,
  variant = "outline",
  className,
  hrefForValue,
}: {
  values: readonly string[];
  label: string;
  variant?: "default" | "secondary" | "outline" | "success" | "warning" | "destructive";
  className?: string;
  hrefForValue?: (value: string) => string | undefined;
}) {
  const unique = [...new Set(values)].filter(Boolean);
  if (unique.length === 0) return null;
  const visible = unique.slice(0, VISIBLE_LIMIT);
  const hidden = unique.slice(VISIBLE_LIMIT);

  return (
    <div className={cn("flex min-w-0 flex-wrap items-center gap-1", className)} aria-label={label}>
      {visible.map((value) => {
        const href = hrefForValue?.(value);
        const chip = <Badge variant={variant}>{value}</Badge>;
        return href ? (
          <Link
            key={value}
            href={href}
            className="focus-visible:ring-ring rounded-sm hover:underline focus-visible:ring-2 focus-visible:outline-none"
          >
            {chip}
          </Link>
        ) : (
          <span key={value}>{chip}</span>
        );
      })}
      {hidden.length ? (
        <span className="relative z-30 shrink-0">
          <Menu modal={false}>
            <MenuTrigger asChild>
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
            </MenuTrigger>
            <MenuContent
              side="top"
              align="start"
              sideOffset={8}
              className="w-max max-w-[min(18rem,calc(100vw-2rem))] p-2"
            >
              <p className="text-muted-foreground mb-1 text-xs font-medium">{label}</p>
              <div className="flex flex-wrap gap-1">
                {unique.map((value) => {
                  const href = hrefForValue?.(value);
                  const chip = <Badge variant={variant}>{value}</Badge>;
                  return href ? (
                    <MenuItem key={value} asChild>
                      <Link href={href} className="focus:bg-accent rounded-sm outline-none">
                        {chip}
                      </Link>
                    </MenuItem>
                  ) : (
                    <span key={value}>{chip}</span>
                  );
                })}
              </div>
            </MenuContent>
          </Menu>
        </span>
      ) : null}
    </div>
  );
}
