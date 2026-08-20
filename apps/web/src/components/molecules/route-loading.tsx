import { Skeleton } from "@/components/atoms/skeleton";

type RouteLoadingProps = {
  /** Accessible label for the status region (already translated by caller). */
  label: string;
};

/**
 * Shared route-level loading shell for segment `loading.tsx` files.
 * Pure presentational: no data fetch, easy to unit-test without Docker.
 */
export function RouteLoading({ label }: RouteLoadingProps) {
  return (
    <div role="status" aria-live="polite" aria-label={label} className="space-y-4">
      <Skeleton className="h-10 w-1/3" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
      <span className="sr-only">{label}</span>
    </div>
  );
}
