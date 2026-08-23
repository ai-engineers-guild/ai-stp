import { describe, expect, it } from "vitest";

import { ApiError, mapHttpError } from "@/lib/api/errors";

/**
 * Typed error mapping for catalog/account UI states (SPEC-022 REQ-2205).
 * Wrong status→code mapping would show "unknown" instead of empty/unauthorized.
 */
describe("mapHttpError", () => {
  it("prefers the wire error code when the body carries one", () => {
    const err = mapHttpError(404, {
      error: { code: "AI_STP_NOT_FOUND", message: "missing object" },
      operation_id: "readComponent",
      request_id: "req_fixture",
    });
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("AI_STP_NOT_FOUND");
    expect(err.message).toBe("missing object");
    expect(err.status).toBe(404);
    expect(err.operationId).toBe("readComponent");
    expect(err.requestId).toBe("req_fixture");
  });

  it("derives code from HTTP status when the body is empty or unknown", () => {
    expect(mapHttpError(401, null).code).toBe("AI_STP_UNAUTHORIZED");
    expect(mapHttpError(403, {}).code).toBe("AI_STP_FORBIDDEN");
    expect(mapHttpError(404, { error: { code: "NOT_A_REAL_CODE" } }).code).toBe("AI_STP_NOT_FOUND");
    expect(mapHttpError(409, null).code).toBe("AI_STP_CONFLICT");
    expect(mapHttpError(412, null).code).toBe("AI_STP_PRECONDITION_FAILED");
    expect(mapHttpError(429, null).code).toBe("AI_STP_RATE_LIMITED");
    expect(mapHttpError(503, null).code).toBe("AI_STP_UNAVAILABLE");
    expect(mapHttpError(0, null).code).toBe("AI_STP_UNAVAILABLE");
    expect(mapHttpError(418, null).code).toBe("AI_STP_UNKNOWN");
  });

  it("reads operation and request ids from response headers as a fallback", () => {
    const headers = new Headers({
      "x-operation-id": "searchComponents",
      "x-request-id": "req_from_header",
    });
    const err = mapHttpError(500, {}, headers);
    expect(err.code).toBe("AI_STP_UNAVAILABLE");
    expect(err.operationId).toBe("searchComponents");
    expect(err.requestId).toBe("req_from_header");
  });
});
