import { cn } from "@/lib/cn";

export function VisibilityLabel({
  visibility,
  publicLabel = "public",
  privateLabel = "private",
  className,
}: {
  visibility: "public" | "private";
  publicLabel?: string | undefined;
  privateLabel?: string | undefined;
  className?: string;
}) {
  const isPrivate = visibility === "private";
  return (
    <span
      className={cn(
        "inline-flex min-h-7 items-center border border-t-0 px-3 py-1 font-mono text-xs shadow-sm",
        isPrivate
          ? "border-orange-500 bg-orange-500 font-semibold text-black"
          : "border-border bg-muted text-muted-foreground",
        className,
      )}
      style={{ clipPath: "polygon(0 0, 100% 0, 100% 78%, 88% 100%, 0 100%)" }}
      data-visibility={visibility}
    >
      {isPrivate ? privateLabel : publicLabel}
    </span>
  );
}
