export type ContextCostEstimate = {
  status: "empty" | "invalid" | "available";
  amount: string | null;
};

const RATE_PATTERN = /^[0-9]+(\.[0-9]+)?$/;

export function estimateContextCost(
  totalTokens: number,
  inputPerMillion: string,
): ContextCostEstimate {
  const raw = inputPerMillion.trim();
  if (raw === "") {
    return { status: "empty", amount: null };
  }
  if (!RATE_PATTERN.test(raw)) {
    return { status: "invalid", amount: null };
  }
  const rate = Number(raw);
  if (!Number.isFinite(rate)) {
    return { status: "invalid", amount: null };
  }
  const amount = (totalTokens * rate) / 1_000_000;
  return { status: "available", amount: amount.toFixed(8) };
}
