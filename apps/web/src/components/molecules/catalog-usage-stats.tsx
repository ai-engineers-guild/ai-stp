import type { CatalogUsageMetrics } from "@/lib/api/generated/types.gen";
import { cn } from "@/lib/cn";
import { isFeatureEnabled } from "@/lib/features/gate";
import { formatUsageCount } from "@/lib/format-usage-count";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme";

export function CatalogUsageStats({
  metrics,
  locale,
  viewsLabel,
  downloadsLabel,
  compact = false,
}: {
  metrics: CatalogUsageMetrics | null | undefined;
  locale: string;
  viewsLabel: string;
  downloadsLabel: string;
  compact?: boolean;
}) {
  if (!isFeatureEnabled("catalog_usage_metrics") || metrics == null) {
    return null;
  }
  const views = formatUsageCount(metrics.detail_views_count, locale);
  const downloads = formatUsageCount(metrics.artifact_downloads_count, locale);
  return (
    <div
      data-ui={UI.catalog.usage}
      className={cn(
        "text-muted-foreground flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1",
        compact ? "text-xs" : "text-sm",
      )}
    >
      <span
        className="inline-flex max-w-full min-w-0 items-center gap-1"
        aria-label={`${viewsLabel}: ${views}`}
      >
        <Icon name="eye" size="sm" />
        <span className="font-mono tabular-nums" aria-hidden="true">
          {views}
        </span>
        {compact ? null : (
          <span className="min-w-0 truncate" aria-hidden="true">
            {viewsLabel}
          </span>
        )}
      </span>
      <span
        className="inline-flex max-w-full min-w-0 items-center gap-1"
        aria-label={`${downloadsLabel}: ${downloads}`}
      >
        <Icon name="download" size="sm" />
        <span className="font-mono tabular-nums" aria-hidden="true">
          {downloads}
        </span>
        {compact ? null : (
          <span className="min-w-0 truncate" aria-hidden="true">
            {downloadsLabel}
          </span>
        )}
      </span>
    </div>
  );
}
