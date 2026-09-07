import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { importAvatarFromIdentity } from "@/lib/api/public-profile";
import { apiRequest } from "@/lib/api/http";
import { sessionCookieValue } from "@/lib/auth/require-session";
import type * as AuthSession from "@/lib/auth/session";

vi.mock("@/lib/api/http", () => ({ apiRequest: vi.fn() }));
vi.mock("@/lib/auth/require-session", () => ({ sessionCookieValue: vi.fn() }));
vi.mock("@/lib/auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof AuthSession>()),
  readCsrfToken: vi.fn(() => Promise.resolve("form-csrf")),
}));

describe("profile avatar server action", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(sessionCookieValue).mockResolvedValue("server-cookie-session");
  });
  it("uses the server session and returns the processed asset", async () => {
    const avatar = { avatar_asset_id: "avatar_test", public_url: "/v1/media/avatars/avatar_test" };
    vi.mocked(apiRequest).mockResolvedValue(avatar);
    await expect(importAvatarFromIdentity("form-csrf", "github")).resolves.toEqual({
      ok: true,
      avatar,
    });
    expect(apiRequest).toHaveBeenCalledWith(
      "/v1/account/public-profile/avatar/from-identity",
      expect.objectContaining({
        sessionToken: "server-cookie-session",
        body: { provider: "github" },
      }),
    );
  });
  it("refuses an invalid CSRF token before forwarding", async () => {
    await expect(importAvatarFromIdentity("wrong-csrf", "google")).resolves.toMatchObject({
      ok: false,
    });
    expect(apiRequest).not.toHaveBeenCalled();
  });
  it("keeps a typed provider failure across serialization", async () => {
    const error = new ApiError({
      code: "AI_STP_UNAVAILABLE",
      status: 503,
      message: "avatar source fetch failed",
    });
    vi.mocked(apiRequest).mockRejectedValue(error);
    await expect(importAvatarFromIdentity("form-csrf", "github")).resolves.toMatchObject({
      ok: false,
      code: error.code,
      status: error.status,
      message: error.message,
    });
  });
});
