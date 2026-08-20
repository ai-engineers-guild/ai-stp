import { afterEach, describe, expect, it, vi } from "vitest";

import { asAccountId, asDeviceId } from "@/lib/brands";

describe("web session (ADR-0041)", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  it("round-trips a signed session token", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USE_MOCKS", "true");
    const { createSessionToken, parseSessionToken } = await import("@/lib/auth/session");
    const accountId = asAccountId("account_01JQZK7B8N4M6P2R9T5V0X3Y7Z");
    const deviceId = asDeviceId("device_01JQZK7B8N4M6P2R9T5V0X3Y7Z");
    const { token, session } = createSessionToken(accountId, deviceId);
    const parsed = parseSessionToken(token);
    expect(parsed?.accountId).toBe(session.accountId);
    expect(parsed?.deviceId).toBe(session.deviceId);
  });

  it("rejects tampered tokens", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USE_MOCKS", "true");
    const { createSessionToken, parseSessionToken } = await import("@/lib/auth/session");
    const { token } = createSessionToken(asAccountId("account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"));
    expect(parseSessionToken(`${token}x`)).toBeNull();
  });

  it("rejects expired tokens", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USE_MOCKS", "true");
    const { createSessionToken, parseSessionToken } = await import("@/lib/auth/session");
    const { token } = createSessionToken(asAccountId("account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"));
    // Force expiry by rewriting the payload while keeping a valid signature shape:
    // parse must fail when expiresAt is in the past (REQ-2308).
    const [payload] = token.split(".");
    if (payload === undefined || payload.length === 0) {
      throw new Error("expected signed session token to carry a payload segment");
    }
    const body = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as {
      accountId: string;
      deviceId: string | null;
      expiresAt: number;
    };
    body.expiresAt = Date.now() - 1_000;
    const secret = "dev-only-change-me-to-a-long-random-string";
    const { createHmac } = await import("node:crypto");
    const newPayload = Buffer.from(JSON.stringify(body), "utf8").toString("base64url");
    const signature = createHmac("sha256", secret).update(newPayload).digest("base64url");
    expect(parseSessionToken(`${newPayload}.${signature}`)).toBeNull();
  });
});
