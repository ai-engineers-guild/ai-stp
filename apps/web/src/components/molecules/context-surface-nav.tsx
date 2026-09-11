import {
  CONTEXT_SURFACES,
  CORPORATE_SURFACES,
  type ContextSurfaceKey,
  type CorporateSurfaceKey,
} from "@/lib/context-surfaces";
import type { ActiveContext } from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";
import { hasCapability } from "@/lib/product-context";
import type { ProductContextStatus } from "@/lib/product-context";
import { UI } from "@/lib/ui-selectors";

export function ContextSurfaceNav({
  context,
  status,
  labels,
  reserveWhenHidden = false,
}: {
  context: ActiveContext;
  status: ProductContextStatus;
  labels: Record<ContextSurfaceKey | CorporateSurfaceKey, string> & { navigation: string };
  reserveWhenHidden?: boolean;
}) {
  if (status !== "ready") {
    return reserveWhenHidden ? (
      <nav
        aria-hidden="true"
        className="border-border bg-background mx-auto max-w-6xl border-b px-4 py-2 sm:px-6"
      />
    ) : null;
  }
  const visible = [...CONTEXT_SURFACES, ...CORPORATE_SURFACES].filter((surface) =>
    hasCapability(context, surface.capability),
  );
  return (
    <nav
      data-ui={UI.context.navigation}
      aria-label={labels.navigation}
      className="border-border bg-background mx-auto flex max-w-6xl gap-1 overflow-x-auto border-b px-4 py-2 sm:px-6"
    >
      {visible.map((surface) => (
        <Link
          key={surface.href}
          href={surface.href}
          className="text-muted-foreground hover:text-foreground rounded-md px-2 py-1 text-xs whitespace-nowrap transition-colors"
        >
          {labels[surface.key]}
        </Link>
      ))}
    </nav>
  );
}
