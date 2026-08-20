"use client";

import { useId, useState } from "react";

import type { ContextCostLabels } from "@/components/organisms/context-budget-labels";
import { estimateContextCost } from "@/lib/estimate-context-cost";

export type { ContextCostLabels };

export function ContextCostCalculator({
  totalTokens,
  labels,
}: {
  totalTokens: number;
  labels: ContextCostLabels;
}) {
  const fieldId = useId();
  const [rate, setRate] = useState("");
  const result = estimateContextCost(totalTokens, rate);

  return (
    <div className="space-y-2">
      <label htmlFor={fieldId} className="text-sm font-medium">
        {labels.rateLabel}
      </label>
      <input
        id={fieldId}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={rate}
        onChange={(event) => {
          setRate(event.target.value);
        }}
        className="border-border bg-background focus-visible:ring-ring w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none"
      />
      <p className="text-muted-foreground text-xs">{labels.hint}</p>
      {result.status === "available" ? (
        <p className="font-mono text-sm">
          {labels.estimate}: {result.amount}
        </p>
      ) : (
        <p className="text-muted-foreground text-sm">
          {result.status === "invalid" ? labels.invalid : labels.empty}
        </p>
      )}
    </div>
  );
}
