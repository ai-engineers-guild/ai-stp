import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { Icon, type IconName } from "@/theme";

/** Quiet bordered note for policy explanations; not an alert, so it stays a
 * plain region — assistive tech reads it in document order, not as a popup. */
export function InfoNote({
  icon = "info",
  children,
  className,
}: {
  icon?: IconName;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-md border border-border bg-muted/30 px-4 py-3",
        className,
      )}
    >
      <Icon name={icon} size="sm" className="mt-0.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 text-sm text-muted-foreground">{children}</div>
    </div>
  );
}
