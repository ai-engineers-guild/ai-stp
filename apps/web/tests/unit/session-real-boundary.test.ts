import { afterEach, describe, expect, it, vi } from "vitest";

const cookieStore = {
  get: vi.fn(),
};
const readAuthMe = vi.fn();

vi.mock("next/headers", () => ({
  cookies: vi.fn(() => Promise.resolve(cookieStore)),
}));
vi.mock("@/lib/api/auth-me", () => ({ readAuthMe }));

describe("real session boundary", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    cookieStore.get.mockReset();
    readAuthMe.mockReset();
  });

  it("does not accept a locally signed fixture token in real mode", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://api.test:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USE_MOCKS", "false");
    vi.stubEnv("AI_STP_MOCK_AUTH", "false");

    const { asAccountId } = await import("@/lib/brands");
    const { createSessionToken, readSession, SESSION_COOKIE } = await import("@/lib/auth/session");
    const { token } = createSessionToken(asAccountId("account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"));
    cookieStore.get.mockImplementation((name: string) =>
      name === SESSION_COOKIE ? { value: token } : undefined,
    );
    readAuthMe.mockResolvedValue({
      account_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
      account_status: "active",
      device_id: null,
    });

    const session = await readSession();

    expect(readAuthMe).toHaveBeenCalledOnce();
    expect(session?.accountId).toBe("account_01JQZK7B8N4M6P2R9T5V0X3Y7Z");
  });
});
