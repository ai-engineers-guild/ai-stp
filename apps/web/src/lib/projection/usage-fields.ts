import { field, type MachineBlock } from "@/lib/projection/machine-document";

type UsageMetrics = {
  detail_views_count: number;
  artifact_downloads_count: number;
};

export function usageMachineFields(
  metrics: UsageMetrics | null | undefined,
  labels: { detailViews?: string; artifactDownloads?: string },
): MachineBlock[] {
  if (metrics == null) return [];
  return [
    field(labels.detailViews ?? "detail_views_count", String(metrics.detail_views_count)),
    field(
      labels.artifactDownloads ?? "artifact_downloads_count",
      String(metrics.artifact_downloads_count),
    ),
  ];
}

export function usageFromCounts(
  views: number | null | undefined,
  downloads: number | null | undefined,
): UsageMetrics | null {
  if (views == null || downloads == null) return null;
  return { detail_views_count: views, artifact_downloads_count: downloads };
}
