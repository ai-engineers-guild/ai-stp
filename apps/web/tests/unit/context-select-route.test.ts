import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { privateApiRequest } from "@/lib/api/http";

vi.mock("@/lib/env", () => ({ getEnv: () => ({ AI_STP_USE_MOCKS: true }) }));
vi.mock("@/lib/api/http", () => ({
  privateApiRequest: vi.fn(),
}));

const contextRequest = vi.mocked(privateApiRequest);

describe("api/context/select route", () => {
  afterEach(() => {
    vi.resetModules();
    contextRequest.mockReset();
  });

  it.each([
    ["malformed JSON", "{"],
    ["null JSON", "null"],
    ["array JSON", "[]"],
    ["unknown fields", JSON.stringify({ organization_id: null, role: "admin" })],
    ["invalid organization", JSON.stringify({ organization_id: "organization_forged" })],
    [
      "local organization combination",
      JSON.stringify({ mode: "local", organization_id: "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z" }),
    ],
  ])("rejects %s before writing a cookie", async (_label, body) => {
    const { POST } = await import("@/app/api/context/select/route");
    const response = await POST(
      new Request("http://localhost/api/context/select", { method: "POST", body }),
    );
    expect(response.status).toBe(400);
    expect(contextRequest).not.toHaveBeenCalled();
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("does not persist an organization selected outside the authenticated membership", async () => {
    contextRequest.mockRejectedValue(
      new ApiError({ code: "AI_STP_FORBIDDEN", message: "denied", status: 403 }),
    );
    const { POST } = await import("@/app/api/context/select/route");
    const response = await POST(
      new Request("http://localhost/api/context/select", {
        method: "POST",
        body: JSON.stringify({ organization_id: "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z" }),
      }),
    );
    expect(response.status).toBe(403);
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("persists only the server-authorized organization context", async () => {
    contextRequest.mockResolvedValue({
      mode: "corporate",
      organization_id: "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    });
    const { POST } = await import("@/app/api/context/select/route");
    const response = await POST(
      new Request("http://localhost/api/context/select", {
        method: "POST",
        body: JSON.stringify({ organization_id: "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z" }),
      }),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain(
      "ai_stp_organization_id=organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    );
    expect(contextRequest).toHaveBeenCalledWith("/v1/context", {
      headers: { "X-AI-STP-Organization-Id": "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z" },
      baseUrl: "http://127.0.0.1:8000",
    });
  });

  it("starts a loopback session before persisting local context", async () => {
    contextRequest.mockResolvedValue({
      session: "local-session",
      csrf: "local-csrf",
      expires_at: "2099-01-01T00:00:00.000Z",
    });
    const { POST } = await import("@/app/api/context/select/route");
    const response = await POST(
      new Request("http://localhost/api/context/select", {
        method: "POST",
        body: JSON.stringify({ mode: "local", organization_id: null }),
      }),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain("ai_stp_product_mode=local");
    expect(response.headers.get("set-cookie")).toContain("ai_stp_local_session=local-session");
    expect(contextRequest).toHaveBeenCalledWith("/v1/local/session", {
      method: "POST",
      baseUrl: "http://127.0.0.1:8000",
    });
  });

  it("rejects cross-origin session creation before spawning or changing context", async () => {
    const { POST } = await import("@/app/api/context/select/route");
    const response = await POST(
      new Request("http://localhost/api/context/select", {
        method: "POST",
        headers: { Origin: "https://attacker.invalid" },
        body: JSON.stringify({ mode: "local" }),
      }),
    );
    expect(response.status).toBe(403);
    expect(contextRequest).not.toHaveBeenCalled();
    expect(response.headers.get("set-cookie")).toBeNull();
  });
});
