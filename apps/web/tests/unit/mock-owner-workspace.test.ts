import { beforeEach, describe, expect, it } from "vitest";

import { mockFetch, mockResultToData } from "@/lib/api/mock-transport";

describe("mock owner workspace transport", () => {
  beforeEach(() => {
    // no-op: mock transport is pure
  });

  it("lists owned objects for an authenticated session", () => {
    const result = mockFetch("GET", "/v1/owner/objects", {
      headers: { Authorization: "Bearer mock-session" },
    });
    const body = mockResultToData<{ items: { stable_id: string }[] }>(result);
    expect(body.items.length).toBeGreaterThan(0);
    expect(body.items[0]?.stable_id).toMatch(/^component_/);
  });

  it("rejects unauthenticated owner reads", () => {
    const result = mockFetch("GET", "/v1/owner/objects", { headers: {} });
    expect(result.status).toBe(401);
  });

  it("starts a publication plan without a browser passport body", () => {
    const result = mockFetch(
      "POST",
      "/v1/owner/objects/component/component_01JQZK7B8N4M6P2R9T5V0X3Y7Z/versions/1.0/publication-plans",
      {
        headers: { Authorization: "Bearer mock-session" },
        body: JSON.stringify({
          schema_version: 1,
          device_id: "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
          idempotency_key: "a".repeat(32),
        }),
      },
    );
    expect(result.status).toBe(201);
    const body = mockResultToData<{ plan_id: string; state: string }>(result);
    expect(body.plan_id).toMatch(/^plan_/);
    expect(body.state).toBe("ready");
  });

  it("accepts grant invitation and lists grants", () => {
    const accept = mockFetch(
      "POST",
      "/v1/grants/invitations/invite_01JQZK7B8N4M6P2R9T5V0X3Y7Z/accept",
      {
        headers: { Authorization: "Bearer mock-session" },
        body: JSON.stringify({
          schema_version: 1,
          token: "secret-token",
          idempotency_key: "b".repeat(32),
        }),
      },
    );
    expect(accept.status).toBe(200);
    const grants = mockFetch("GET", "/v1/grants", {
      headers: { Authorization: "Bearer mock-session" },
    });
    const body = mockResultToData<{ invitations: unknown[]; grants: unknown[] }>(grants);
    expect(body.invitations.length).toBeGreaterThan(0);
    expect(body.grants.length).toBeGreaterThan(0);
  });

  it("serves staff worklist in mock mode", () => {
    const result = mockFetch("GET", "/v1/staff/reports", {
      headers: { Authorization: "Bearer mock-session" },
    });
    const body = mockResultToData<{ items: { case_id: string }[] }>(result);
    expect(body.items[0]?.case_id).toMatch(/^case_/);
  });

  it("uploads component media and persists presentation media on PUT", () => {
    const stableId = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
    const upload = mockFetch("POST", `/v1/owner/objects/component/${stableId}/presentation/media`, {
      headers: {
        Authorization: "Bearer mock-session",
        "Content-Type": "image/png",
      },
    });
    expect(upload.status).toBe(201);
    const uploaded = mockResultToData<{ public_url: string; kind: string }>(upload);
    expect(uploaded.kind).toBe("image");
    expect(uploaded.public_url).toMatch(/^\/v1\/media\/component\//);

    const saved = mockFetch("PUT", `/v1/owner/objects/component/${stableId}/presentation`, {
      headers: { Authorization: "Bearer mock-session" },
      body: JSON.stringify({
        schema_version: 1,
        bio: "Persisted mock bio",
        media: [
          {
            kind: "image",
            url: uploaded.public_url,
            alt: "Cover",
            caption: "",
          },
        ],
      }),
    });
    expect(saved.status).toBe(200);

    const read = mockFetch("GET", `/v1/owner/objects/component/${stableId}/presentation`, {
      headers: { Authorization: "Bearer mock-session" },
    });
    const presentation = mockResultToData<{ bio: string; media: { url: string; alt: string }[] }>(
      read,
    );
    expect(presentation.bio).toBe("Persisted mock bio");
    expect(presentation.media[0]?.url).toBe(uploaded.public_url);
    expect(presentation.media[0]?.alt).toBe("Cover");
  });
});
