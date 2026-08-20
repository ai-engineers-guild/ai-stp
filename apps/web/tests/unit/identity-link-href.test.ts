import { describe, expect, it } from "vitest";

/**
 * Mirrors the browser step-up start URL from IdentityList.
 * Server-side fetch must never start OAuth: the handshake cookie belongs to the browser.
 */
function linkHref(provider: "google" | "github", returnTo: string): string {
  const params = new URLSearchParams({ return_to: returnTo });
  return `/v1/auth/link/${provider}?${params.toString()}`;
}

describe("step-up OAuth link href", () => {
  it("starts link via browser-owned API path with return_to", () => {
    expect(linkHref("google", "/en/account")).toBe(
      "/v1/auth/link/google?return_to=%2Fen%2Faccount",
    );
    expect(linkHref("github", "/ru/account")).toBe(
      "/v1/auth/link/github?return_to=%2Fru%2Faccount",
    );
  });

  it("never points at a Next server action path", () => {
    const href = linkHref("google", "/en/account");
    expect(href.startsWith("/v1/auth/link/")).toBe(true);
    expect(href.includes("account")).toBe(true);
    expect(href.startsWith("/api/")).toBe(false);
  });
});
