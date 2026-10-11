import { Skeleton } from "@/components/atoms/skeleton";

/** Loading placeholder shared by the provider connectors. */
export function ConnectorSkeleton({ label }: { label: string }) {
  return (
    <div className="space-y-3" role="status" aria-label={label} aria-busy="true">
      <Skeleton className="h-5 w-48" />
      <Skeleton className="h-16 w-full rounded-lg" />
      <Skeleton className="h-16 w-full rounded-lg" />
    </div>
  );
}
