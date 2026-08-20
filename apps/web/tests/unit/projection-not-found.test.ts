import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { isNotFoundError, orNotFound } from "@/lib/projection/not-found";

describe("machine not-found mapping (REQ-3626)", () => {
  it("treats missing catalog records as absent documents", async () => {
    expect(
      isNotFoundError(new ApiError({ code: "AI_STP_NOT_FOUND", message: "gone", status: 404 })),
    ).toBe(true);
    expect(
      await orNotFound(
        Promise.reject(new ApiError({ code: "AI_STP_NOT_FOUND", message: "gone", status: 404 })),
      ),
    ).toBeNull();
  });

  it("does not swallow unavailable errors", async () => {
    await expect(
      orNotFound(
        Promise.reject(new ApiError({ code: "AI_STP_UNAVAILABLE", message: "down", status: 503 })),
      ),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
