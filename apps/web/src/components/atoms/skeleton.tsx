import { cn } from "@/lib/cn";

/** Loading placeholder — muted surface, pulse (respects reduced motion). */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("bg-muted animate-pulse rounded-md motion-reduce:animate-none", className)}
      aria-hidden="true"
      {...props}
    />
  );
}
