import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { Icon, type IconName } from "@/theme";

/**
 * Bordered settings card: icon + title + description header, an optional
 * `aside` (status badge, toggle) on the same row, then the body below a
 * divider. `header` replaces the default header entirely for composite rows.
 */
export function SettingsSection({
  icon,
  title,
  description,
  aside,
  header,
  className,
  children,
}: {
  icon?: IconName | undefined;
  title?: string | undefined;
  description?: string | undefined;
  aside?: ReactNode;
  header?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn("border-border rounded-lg border p-5 sm:p-6", className)}>
      {header ?? (
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            {icon ? (
              <span
                aria-hidden
                className="border-border bg-muted/40 text-muted-foreground grid size-10 shrink-0 place-items-center rounded-md border"
              >
                <Icon name={icon} size="sm" />
              </span>
            ) : null}
            <div className="min-w-0">
              <h2 className="text-base font-medium">{title}</h2>
              {description ? (
                <p className="text-muted-foreground mt-0.5 text-sm">{description}</p>
              ) : null}
            </div>
          </div>
          {aside ? <div className="flex shrink-0 items-center gap-3">{aside}</div> : null}
        </div>
      )}
      <div className="border-border mt-5 border-t pt-5">{children}</div>
    </section>
  );
}
