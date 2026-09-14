import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequestBinary } from "@/lib/api/http";
import { mockFetch } from "@/lib/api/mock-transport";
import { readMockCorporateMedia } from "@/lib/api/mock-corporate";
import { resetEnvCache } from "@/lib/env";
import { GET as deliverCorporateMedia } from "@/app/v1/media/avatars/[assetId]/route";
import { POST as corporateMediaBff } from "@/app/api/corporate/organizations/[organizationId]/profiles/[kind]/[id]/media/route";

vi.mock("next/headers", () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === "ai_stp_session"
          ? { value: "offline-session" }
          : name === "ai_stp_csrf"
            ? { value: "offline-csrf" }
            : undefined,
    }),
}));

const organizationId = "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const teamId = "operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const uploadPath = `/v1/corporate/organizations/${organizationId}/profiles/team/${teamId}/media`;
const profilePath = `/v1/corporate/organizations/${organizationId}/entity-profiles/team/${teamId}`;
const query = new URLSearchParams({
  purpose: "media",
  expected_revision: "0",
  authorization_revision: "1",
});
const avatarQuery = new URLSearchParams({
  purpose: "avatar",
  expected_revision: "0",
  authorization_revision: "1",
});
const headers = {
  Authorization: "Bearer mock-session",
  "Content-Type": "image/png",
  "Idempotency-Key": "corporate-mock-upload-test-1",
};

function stubMockEnv(): void {
  vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
  vi.stubEnv("AI_STP_API_BASE_URL", "http://api.test:8000");
  vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
  vi.stubEnv("AI_STP_USE_MOCKS", "true");
  vi.stubEnv("AI_STP_MOCK_AUTH", "true");
  resetEnvCache();
}

afterEach(() => {
  vi.unstubAllEnvs();
  resetEnvCache();
});

describe("offline corporate media fixture", () => {
  it("routes browser bytes through the same-origin BFF and serves the stored asset", async () => {
    stubMockEnv();
    const bytes = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]);
    const request = new Request(
      `http://localhost/api/corporate/organizations/${organizationId}/profiles/team/${teamId}/media?${query.toString()}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "image/png",
          "X-CSRF-Token": "offline-csrf",
          "Idempotency-Key": "corporate-bff-upload-test-1",
        },
        body: bytes,
      },
    );
    const response = await corporateMediaBff(request, {
      params: Promise.resolve({ organizationId, kind: "team", id: teamId }),
    });
    expect(response.status).toBe(200);
    const receipt = (await response.json()) as { avatar_asset_id: string; public_url: string };
    expect(receipt.public_url).toBe(`/v1/media/avatars/${receipt.avatar_asset_id}`);

    const delivery = await deliverCorporateMedia(
      new Request(`http://localhost${receipt.public_url}`),
      {
        params: Promise.resolve({ assetId: receipt.avatar_asset_id }),
      },
    );
    expect(delivery.status).toBe(200);
    expect(delivery.headers.get("content-type")).toContain("image/png");
    expect([...new Uint8Array(await delivery.arrayBuffer())]).toEqual([...bytes]);
  });

  it("does not serve synthetic fixture assets in real transport mode", async () => {
    stubMockEnv();
    vi.stubEnv("AI_STP_USE_MOCKS", "false");
    resetEnvCache();
    const response = await deliverCorporateMedia(
      new Request("http://localhost/v1/media/avatars/avatar_aaaaaaaaaaaaaaaaaaaaaaaa"),
      {
        params: Promise.resolve({ assetId: "avatar_aaaaaaaaaaaaaaaaaaaaaaaa" }),
      },
    );
    expect(response.status).toBe(404);
  });

  it("preserves binary bytes, replays the receipt, delivers the asset, and attaches it on PUT", async () => {
    stubMockEnv();
    const bytes = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]);
    const path = `${uploadPath}?${avatarQuery.toString()}`;
    const first = await apiRequestBinary<{
      avatar_asset_id: string;
      media_id: string;
      public_url: string;
      kind: "image" | "video";
      size_bytes: number;
    }>(path, {
      contentType: "image/png",
      body: bytes.buffer,
      sessionToken: "offline-session",
      headers: { "Idempotency-Key": headers["Idempotency-Key"] },
    });

    expect(first).toMatchObject({
      media_id: first.avatar_asset_id,
      public_url: `/v1/media/avatars/${first.avatar_asset_id}`,
      kind: "image",
      size_bytes: bytes.byteLength,
    });
    expect(readMockCorporateMedia(first.avatar_asset_id)).toMatchObject({
      contentType: "image/png",
    });
    expect([...(readMockCorporateMedia(first.avatar_asset_id)?.body ?? [])]).toEqual([...bytes]);

    const replay = await apiRequestBinary(path, {
      contentType: "image/png",
      body: bytes.buffer,
      sessionToken: "offline-session",
      headers: { "Idempotency-Key": headers["Idempotency-Key"] },
    });
    expect(replay).toEqual(first);

    const write = mockFetch("PUT", profilePath, {
      headers,
      body: JSON.stringify({
        schema_version: 1,
        fields: {
          description: "Synthetic uploaded profile",
          avatar_asset_id: first.avatar_asset_id,
          links: [],
          media: [{ kind: "image", url: first.public_url, alt: "Fixture upload", caption: "" }],
        },
        expected_revision: 0,
        authorization_revision: 1,
        idempotency_key: "00000000-0000-4000-8000-000000000001",
      }),
    });
    expect(write.status).toBe(200);
    expect(write.body).toMatchObject({
      revision: 1,
      avatar_url: first.public_url,
      fields: { avatar_asset_id: first.avatar_asset_id },
    });
    const persisted = mockFetch("GET", profilePath, { headers });
    expect(persisted.status).toBe(200);
    expect(persisted.body).toMatchObject({
      revision: 1,
      avatar_url: first.public_url,
      fields: {
        avatar_asset_id: first.avatar_asset_id,
        media: [{ url: first.public_url, alt: "Fixture upload" }],
      },
    });

    const clearBody = JSON.stringify({
      schema_version: 1,
      fields: {
        description: "Synthetic uploaded profile",
        avatar_asset_id: null,
        links: [],
        media: [{ kind: "image", url: first.public_url, alt: "Fixture upload", caption: "" }],
      },
      expected_revision: 1,
      authorization_revision: 1,
      idempotency_key: "00000000-0000-4000-8000-000000000002",
    });
    const cleared = mockFetch("PUT", profilePath, { headers, body: clearBody });
    expect(cleared.status).toBe(200);
    expect(cleared.body).toMatchObject({ revision: 2, avatar_url: null });
    const clearReplay = mockFetch("PUT", profilePath, { headers, body: clearBody });
    expect(clearReplay.status).toBe(200);
    expect(clearReplay.body).toEqual(cleared.body);
    const clearedProfile = mockFetch("GET", profilePath, { headers });
    expect(clearedProfile.body).toMatchObject({ revision: 2, avatar_url: null });
  });

  it("rejects unauthenticated, empty, stale, and conflicting fixture uploads", () => {
    const unauthenticated = mockFetch("POST", uploadPath, {
      query,
      headers: { "Content-Type": "image/png", "Idempotency-Key": headers["Idempotency-Key"] },
      body: new Uint8Array([1]),
    });
    expect(unauthenticated.status).toBe(401);

    const empty = mockFetch("POST", uploadPath, {
      query,
      headers,
      body: new Uint8Array(),
    });
    expect(empty.status).toBe(400);

    const stale = mockFetch("POST", uploadPath, {
      query: new URLSearchParams({
        purpose: "media",
        expected_revision: "99",
        authorization_revision: "1",
      }),
      headers: { ...headers, "Idempotency-Key": "corporate-mock-upload-stale-1" },
      body: new Uint8Array([1]),
    });
    expect(stale.status).toBe(409);

    const conflicting = mockFetch("POST", uploadPath, {
      query,
      headers: { ...headers, "Idempotency-Key": headers["Idempotency-Key"] },
      body: new Uint8Array([2]),
    });
    expect(conflicting.status).toBe(409);
  });
});
