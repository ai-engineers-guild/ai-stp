import { ApiError } from "@/lib/api/errors";

/** Preserve failure categories while keeping unavailable budgets out of numeric displays. */
export async function loadContextBudget<T>(
  read: Promise<T>,
): Promise<{ budget: T | null; failure: string | null }> {
  try {
    return { budget: await read, failure: null };
  } catch (error) {
    const failure =
      error instanceof ApiError && error.code === "AI_STP_VALIDATION_ERROR"
        ? "invalid_graph"
        : error instanceof ApiError && error.code === "AI_STP_NOT_FOUND"
          ? "artifact_unavailable"
          : "dependency_unavailable";
    return { budget: null, failure };
  }
}
