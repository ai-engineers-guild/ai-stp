import { afterEach, describe, expect, it, vi } from "vitest";

import { COMPONENT_MEDIA_MAX_BYTES } from "@/lib/component-media";

async function jsonBody(response: Response): Promise<unknown> {
  return JSON.parse(await response.text()) as unknown;
}

vi.mock("@/lib/auth/require-session", () => ({
  sessionCookieValue: vi.fn(() => Promise.resolve("mock-session")),
}));

function stubEnv(): void {
  vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
  vi.stubEnv("AI_STP_API_BASE_URL", "http://api.test:8000");
  vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
  vi.stubEnv("AI_STP_USE_MOCKS", "true");
  vi.stubEnv("AI_STP_MOCK_AUTH", "true");
}

describe("component media binary route", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    vi.doUnmock("@/lib/api/http");
  });

  it("forwards supported image bytes and returns a public media path", async () => {
    stubEnv();
    const { POST } = await import("@/app/api/objects/component/[stableId]/media/route");
    const response = await POST(
      new Request("http://localhost/api/objects/component/component_01TESTSTABILITY/media", {
        method: "POST",
        headers: { "Content-Type": "image/png" },
        body: new Uint8Array([137, 80, 78, 71]),
      }),
      { params: Promise.resolve({ stableId: "component_01TESTSTABILITY" }) },
    );

    expect(response.status).toBe(201);
    const body = await jsonBody(response);
    expect(body).toMatchObject({
      kind: "image",
      state: "ready",
    });
    if (!body || typeof body !== "object" || !("public_url" in body)) {
      throw new Error("upload response has no public_url");
    }
    expect(body.public_url).toMatch(/^\/v1\/media\/component\//);
  });

  it("rejects unsupported mime before forwarding", async () => {
    stubEnv();
    const { POST } = await import("@/app/api/objects/component/[stableId]/media/route");
    const response = await POST(
      new Request("http://localhost/api/objects/component/component_01TESTSTABILITY/media", {
        method: "POST",
        headers: { "Content-Type": "image/svg+xml" },
        body: "<svg />",
      }),
      { params: Promise.resolve({ stableId: "component_01TESTSTABILITY" }) },
    );

    expect(response.status).toBe(400);
    await expect(jsonBody(response)).resolves.toMatchObject({
      message: "unsupported component media mime type",
    });
  });

  it("rejects invalid stable ids", async () => {
    stubEnv();
    const { POST } = await import("@/app/api/objects/component/[stableId]/media/route");
    const response = await POST(
      new Request("http://localhost/api/objects/component/short/media", {
        method: "POST",
        headers: { "Content-Type": "image/png" },
        body: new Uint8Array([1, 2, 3]),
      }),
      { params: Promise.resolve({ stableId: "short" }) },
    );

    expect(response.status).toBe(400);
  });

  it("rejects payloads over 25 MiB via content-length before forwarding", async () => {
    stubEnv();
    const binary = vi.fn();
    vi.doMock("@/lib/api/http", () => ({
      apiRequestBinary: binary,
    }));
    vi.resetModules();
    vi.doMock("@/lib/auth/require-session", () => ({
      sessionCookieValue: vi.fn(() => Promise.resolve("mock-session")),
    }));
    const { POST } = await import("@/app/api/objects/component/[stableId]/media/route");
    const response = await POST(
      new Request("http://localhost/api/objects/component/component_01TESTSTABILITY/media", {
        method: "POST",
        headers: {
          "Content-Type": "image/png",
          "Content-Length": String(COMPONENT_MEDIA_MAX_BYTES + 1),
        },
        body: new Uint8Array([1, 2, 3]),
      }),
      { params: Promise.resolve({ stableId: "component_01TESTSTABILITY" }) },
    );

    expect(response.status).toBe(413);
    await expect(jsonBody(response)).resolves.toMatchObject({
      message: "component media exceeds 25 MiB limit",
    });
    expect(binary).not.toHaveBeenCalled();
  });

  it("rejects empty payloads", async () => {
    stubEnv();
    const { POST } = await import("@/app/api/objects/component/[stableId]/media/route");
    const response = await POST(
      new Request("http://localhost/api/objects/component/component_01TESTSTABILITY/media", {
        method: "POST",
        headers: { "Content-Type": "image/png" },
        body: new Uint8Array([]),
      }),
      { params: Promise.resolve({ stableId: "component_01TESTSTABILITY" }) },
    );

    expect(response.status).toBe(400);
    await expect(jsonBody(response)).resolves.toMatchObject({
      message: "empty component media payload",
    });
  });

  it("maps upstream API errors without leaking internals", async () => {
    stubEnv();
    vi.doMock("@/lib/api/http", async () => {
      const { ApiError } = await import("@/lib/api/errors");
      return {
        apiRequestBinary: vi.fn(() =>
          Promise.reject(
            new ApiError({
              code: "AI_STP_NOT_FOUND",
              message: "Not Found",
              status: 404,
            }),
          ),
        ),
      };
    });
    vi.resetModules();
    vi.doMock("@/lib/auth/require-session", () => ({
      sessionCookieValue: vi.fn(() => Promise.resolve("mock-session")),
    }));
    const { POST } = await import("@/app/api/objects/component/[stableId]/media/route");
    const response = await POST(
      new Request("http://localhost/api/objects/component/component_01TESTSTABILITY/media", {
        method: "POST",
        headers: { "Content-Type": "image/png" },
        body: new Uint8Array([137, 80, 78, 71]),
      }),
      { params: Promise.resolve({ stableId: "component_01TESTSTABILITY" }) },
    );

    expect(response.status).toBe(404);
    await expect(jsonBody(response)).resolves.toEqual({
      message: "Not Found",
      code: "AI_STP_NOT_FOUND",
    });
  });

  it("maps unexpected upstream failures to a stable 502", async () => {
    stubEnv();
    vi.doMock("@/lib/api/http", () => ({
      apiRequestBinary: vi.fn(() => Promise.reject(new Error("socket hang up"))),
    }));
    vi.resetModules();
    vi.doMock("@/lib/auth/require-session", () => ({
      sessionCookieValue: vi.fn(() => Promise.resolve("mock-session")),
    }));
    const { POST } = await import("@/app/api/objects/component/[stableId]/media/route");
    const response = await POST(
      new Request("http://localhost/api/objects/component/component_01TESTSTABILITY/media", {
        method: "POST",
        headers: { "Content-Type": "video/webm" },
        body: new Uint8Array([1, 2, 3, 4]),
      }),
      { params: Promise.resolve({ stableId: "component_01TESTSTABILITY" }) },
    );

    expect(response.status).toBe(502);
    await expect(jsonBody(response)).resolves.toEqual({
      message: "component media upload failed",
    });
  });
});
