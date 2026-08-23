/**
 * Typed API error mapping for observable UI states (REQ-2205).
 */

export type ApiErrorCode =
  | "AI_STP_NOT_FOUND"
  | "AI_STP_UNAUTHORIZED"
  | "AI_STP_FORBIDDEN"
  | "AI_STP_VALIDATION_ERROR"
  | "AI_STP_PRECONDITION_FAILED"
  | "AI_STP_CONFLICT"
  | "AI_STP_RATE_LIMITED"
  | "AI_STP_DEVICE_REVOKED"
  | "AI_STP_UNAVAILABLE"
  | "AI_STP_UNKNOWN";

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;
  readonly operationId: string | null;
  readonly requestId: string | null;

  constructor(input: {
    code: ApiErrorCode;
    message: string;
    status: number;
    operationId?: string | null;
    requestId?: string | null;
  }) {
    super(input.message);
    this.name = "ApiError";
    this.code = input.code;
    this.status = input.status;
    this.operationId = input.operationId ?? null;
    this.requestId = input.requestId ?? null;
  }
}

export type ReadState<T> =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "empty" }
  | { status: "data"; data: T };

const KNOWN_CODES: readonly ApiErrorCode[] = [
  "AI_STP_NOT_FOUND",
  "AI_STP_UNAUTHORIZED",
  "AI_STP_FORBIDDEN",
  "AI_STP_VALIDATION_ERROR",
  "AI_STP_PRECONDITION_FAILED",
  "AI_STP_CONFLICT",
  "AI_STP_RATE_LIMITED",
  "AI_STP_DEVICE_REVOKED",
  "AI_STP_UNAVAILABLE",
  "AI_STP_UNKNOWN",
];

function asErrorCode(value: unknown): ApiErrorCode {
  if (typeof value !== "string") {
    return "AI_STP_UNKNOWN";
  }
  return (KNOWN_CODES as readonly string[]).includes(value)
    ? (value as ApiErrorCode)
    : "AI_STP_UNKNOWN";
}

function codeFromStatus(status: number): ApiErrorCode {
  if (status === 0 || status >= 500) {
    return "AI_STP_UNAVAILABLE";
  }
  if (status === 401) {
    return "AI_STP_UNAUTHORIZED";
  }
  if (status === 403) {
    return "AI_STP_FORBIDDEN";
  }
  if (status === 404) {
    return "AI_STP_NOT_FOUND";
  }
  if (status === 409) {
    return "AI_STP_CONFLICT";
  }
  if (status === 412) {
    return "AI_STP_PRECONDITION_FAILED";
  }
  if (status === 429) {
    return "AI_STP_RATE_LIMITED";
  }
  return "AI_STP_UNKNOWN";
}

export function mapHttpError(status: number, body: unknown, headers?: Headers): ApiError {
  const record = body !== null && typeof body === "object" ? (body as Record<string, unknown>) : {};
  const errorObj =
    record["error"] !== null && typeof record["error"] === "object"
      ? (record["error"] as Record<string, unknown>)
      : {};
  const codeFromBody = asErrorCode(errorObj["code"]);
  const message =
    typeof errorObj["message"] === "string"
      ? errorObj["message"]
      : status === 0
        ? "API unavailable"
        : `HTTP ${String(status)}`;
  const operationId =
    (typeof record["operation_id"] === "string" ? record["operation_id"] : null) ??
    headers?.get("x-operation-id") ??
    null;
  const requestId =
    (typeof record["request_id"] === "string" ? record["request_id"] : null) ??
    headers?.get("x-request-id") ??
    null;
  const code = codeFromBody === "AI_STP_UNKNOWN" ? codeFromStatus(status) : codeFromBody;
  return new ApiError({ code, message, status, operationId, requestId });
}
