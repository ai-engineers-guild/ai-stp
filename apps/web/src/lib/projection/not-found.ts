import { ApiError } from "@/lib/api/errors";

/** Missing catalog/owner records become the same 404 as the human page. */
export function isNotFoundError(error: unknown): boolean {
  return error instanceof ApiError && (error.code === "AI_STP_NOT_FOUND" || error.status === 404);
}

export async function orNotFound<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch (error) {
    if (isNotFoundError(error)) return null;
    throw error;
  }
}
