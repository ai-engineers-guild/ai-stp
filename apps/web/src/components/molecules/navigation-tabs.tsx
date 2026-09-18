import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";

export type NavigationTab = {
  key: string;
  href: string;
  label: ReactNode;
  active: boolean;
  ui?: string;
  external?: boolean;
  prefetch?: boolean;
};

type NavigationTabsProps = {
  items: readonly NavigationTab[];
  ariaLabel: string;
  variant?: "primary" | "secondary";
  className?: string;
  dataUi?: string;
};

const linkBase =
  "relative inline-flex min-h-11 shrink-0 items-center rounded-sm px-3 text-sm font-medium transition-colors duration-[var(--duration-fast)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";

const linkVariants = {
  primary:
    "text-muted-foreground hover:bg-accent hover:text-foreground aria-[current=page]:bg-accent aria-[current=page]:text-foreground aria-[current=page]:after:absolute aria-[current=page]:after:inset-x-5 aria-[current=page]:after:bottom-0 aria-[current=page]:after:h-0.5 aria-[current=page]:after:bg-primary",
  secondary:
    "min-h-14 border-b-2 border-transparent text-muted-foreground hover:text-foreground aria-[current=page]:border-primary aria-[current=page]:text-primary",
} as const;

/** Shareable link-based tabs for shell and section navigation. */
export function NavigationTabs({
  items,
  ariaLabel,
  variant = "secondary",
  className,
  dataUi = UI.navigation.tabs,
}: NavigationTabsProps) {
  return (
    <nav
      data-ui={dataUi}
      aria-label={ariaLabel}
      className={cn(
        "flex min-w-0 items-center",
        variant === "secondary" && "gap-2 overflow-x-auto",
        className,
      )}
    >
      {items.map((item) => {
        const linkClassName = cn(linkBase, linkVariants[variant]);
        const props = {
          "aria-current": item.active ? ("page" as const) : undefined,
          className: linkClassName,
          "data-ui": item.ui,
        };
        return item.external ? (
          <a key={item.key} href={item.href} {...props}>
            {item.label}
          </a>
        ) : (
          <Link key={item.key} href={item.href} prefetch={item.prefetch} {...props}>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
