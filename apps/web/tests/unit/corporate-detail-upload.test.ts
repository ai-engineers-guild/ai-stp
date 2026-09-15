import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { uploadCorporateDetailMedia } from "@/lib/corporate-detail-upload";

const fetchMock = vi.fn<typeof fetch>();
const baseInput = {
  organizationId: "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  resource: "teams" as const,
  resourceId: "operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  csrfToken: "csrf-fixture",
  expectedRevision: 2,
  authorizationRevision: 4,
  idempotencyKey: "corporate-upload-test-1",
};

const response = (body: unknown, ok = true) =>
  ({ ok, json: () => Promise.resolve(body) }) as Response;

const receipt = (id = "avatar_aaaaaaaaaaaaaaaaaaaaaaaa", kind: "image" | "video" = "image") => ({
  schema_version: 1,
  avatar_asset_id: id,
  media_id: id,
  public_url: `/v1/media/avatars/${id}`,
  kind,
  state: "ready",
  size_bytes: 3,
});

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("corporate profile media upload", () => {
  it("rejects MIME types that are invalid for media or avatars before fetch", async () => {
    const unsupported = new File([new Uint8Array([1])], "notes.txt", { type: "text/plain" });
    await expect(
      uploadCorporateDetailMedia({ ...baseInput, purpose: "media" }, unsupported),
    ).rejects.toThrow("invalid media upload");

    const animated = new File([new Uint8Array([1])], "avatar.gif", { type: "image/gif" });
    await expect(
      uploadCorporateDetailMedia({ ...baseInput, purpose: "avatar" }, animated),
    ).rejects.toThrow("invalid media upload");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts media with the scoped revisions, CSRF token and idempotency key", async () => {
    const file = new File([new Uint8Array([1, 2, 3])], "screen.png", { type: "image/png" });
    const body = receipt();
    fetchMock.mockResolvedValueOnce(response(body));

    await expect(
      uploadCorporateDetailMedia({ ...baseInput, purpose: "media" }, file),
    ).resolves.toEqual(body);
    const [requestUrl, init] = fetchMock.mock.calls[0] ?? [];
    expect(requestUrl).toBeDefined();
    if (!requestUrl) throw new Error("upload request was not sent");
    const url = new URL(
      typeof requestUrl === "string"
        ? requestUrl
        : requestUrl instanceof URL
          ? requestUrl.href
          : requestUrl.url,
      "https://ai-stp.test",
    );
    expect(url.pathname).toBe(
      "/api/corporate/organizations/organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z/profiles/team/operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z/media",
    );
    expect(Object.fromEntries(url.searchParams)).toEqual({
      purpose: "media",
      expected_revision: "2",
      authorization_revision: "4",
    });
    expect(init).toMatchObject({
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "image/png",
        "X-CSRF-Token": "csrf-fixture",
        "Idempotency-Key": "corporate-upload-test-1",
      },
      body: file,
    });
  });

  it("forwards the same idempotency key when an avatar upload is replayed", async () => {
    const file = new File([new Uint8Array([1])], "avatar.png", { type: "image/png" });
    const body = receipt("avatar_bbbbbbbbbbbbbbbbbbbbbbbb");
    fetchMock.mockResolvedValue(response(body));

    const first = await uploadCorporateDetailMedia({ ...baseInput, purpose: "avatar" }, file);
    const replay = await uploadCorporateDetailMedia({ ...baseInput, purpose: "avatar" }, file);

    expect(replay).toEqual(first);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    for (const [, init] of fetchMock.mock.calls) {
      expect((init?.headers as Record<string, string>)["Idempotency-Key"]).toBe(
        baseInput.idempotencyKey,
      );
    }
  });

  it("rejects malformed receipts, avatar videos and failed HTTP responses", async () => {
    const file = new File([new Uint8Array([1])], "screen.png", { type: "image/png" });
    fetchMock.mockResolvedValueOnce(
      response({ ...receipt(), public_url: "/v1/media/avatars/avatar_bbbbbbbbbbbbbbbbbbbbbbbb" }),
    );
    await expect(
      uploadCorporateDetailMedia({ ...baseInput, purpose: "media" }, file),
    ).rejects.toThrow();

    fetchMock.mockResolvedValueOnce(response(receipt("avatar_cccccccccccccccccccccccc", "video")));
    await expect(
      uploadCorporateDetailMedia({ ...baseInput, purpose: "avatar" }, file),
    ).rejects.toThrow("invalid media upload response");

    fetchMock.mockResolvedValueOnce(response({}, false));
    await expect(
      uploadCorporateDetailMedia({ ...baseInput, purpose: "media" }, file),
    ).rejects.toThrow("media upload failed");
  });
});
