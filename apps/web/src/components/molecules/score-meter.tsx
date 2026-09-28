import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const SCORE_GRADIENT =
  "linear-gradient(90deg, hsl(var(--destructive)), hsl(var(--warning)), hsl(var(--success)))";

type ScoreMeterProps = {
  percent: number;
  label?: string | undefined;
  valueText?: string | undefined;
  compact?: boolean;
} & Omit<HTMLAttributes<HTMLSpanElement>, "role" | "aria-label" | "aria-valuemin" | "aria-valuemax" | "aria-valuenow" | "aria-valuetext" | "children">;

/** Shared 0-100 score meter: token-gradient bar plus the numeric readout. */
export function ScoreMeter({
  percent,
  label,
  valueText,
  compact = false,
  className,
  ...rest
}: ScoreMeterProps) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <span
      className={cn("inline-flex min-w-0 items-center gap-1.5", className)}
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={clamped}
      aria-valuetext={valueText}
      {...rest}
    >
      <span
        className={cn(
          "bg-muted relative block h-1 overflow-hidden rounded-full",
          compact ? "w-8" : "w-10",
        )}
        aria-hidden="true"
      >
        <span
          data-safety-fill=""
          className="absolute inset-y-0 left-0 overflow-hidden"
          style={{ width: `${clamped}%` }}
        >
          <span
            className={cn("block h-full", compact ? "w-8" : "w-10")}
            style={{ background: SCORE_GRADIENT }}
          />
        </span>
      </span>
      <span className="font-mono text-sm font-medium tabular-nums">{clamped}%</span>
    </span>
  );
}
