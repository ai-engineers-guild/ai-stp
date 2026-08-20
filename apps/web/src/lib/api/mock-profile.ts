/**
 * Mock handlers for public-profile routes (SPEC-028) under AI_STP_USE_MOCKS / MOCK_AUTH.
 */
import { errorBody, FIXTURE_ACCOUNT_ID, seedPublicProfiles } from "@/mocks/fixtures";

type MockResult = { status: number; body: unknown; headers?: Record<string, string> };

type DraftState = {
  revision_id: string;
  content_digest: string;
  display_name: string | null;
  bio: string | null;
  links: Array<{ label: string; url: string }>;
  avatar_asset_id: string | null;
  avatar_url: string | null;
};

const seed = seedPublicProfiles[FIXTURE_ACCOUNT_ID];

/** In-process draft so save → preview works under mocks (e2e / Storybook). */
let mockDraft: DraftState = {
  revision_id: "prevision_mock_draft",
  content_digest: "sha256:mock-draft",
  display_name: seed.display_name,
  bio: seed.bio,
  links: [...seed.links],
  avatar_asset_id: null,
  avatar_url: null,
};

let mockPublished: DraftState = {
  revision_id: "prevision_mock_pub",
  content_digest: "sha256:mock-pub",
  display_name: seed.display_name,
  bio: seed.bio,
  links: [...seed.links],
  avatar_asset_id: null,
  avatar_url: null,
};

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function parseLinks(raw: unknown): Array<{ label: string; url: string }> {
  if (!Array.isArray(raw)) return [];
  const links: Array<{ label: string; url: string }> = [];
  for (const item of raw) {
    if (!item || typeof item !== "object" || Array.isArray(item)) continue;
    const row = item as Record<string, unknown>;
    const label = asString(row.label);
    const url = asString(row.url);
    if (label && url) links.push({ label, url });
  }
  return links;
}

function ownerBody(state: "draft" | "published" | "absent") {
  const fields = {
    display_name: mockDraft.display_name,
    bio: mockDraft.bio,
    links: mockDraft.links,
    avatar_asset_id: mockDraft.avatar_asset_id,
  };
  const publishedFields = {
    display_name: mockPublished.display_name,
    bio: mockPublished.bio,
    links: [...mockPublished.links],
    avatar_asset_id: mockPublished.avatar_asset_id,
  };
  return {
    schema_version: 1,
    account_id: FIXTURE_ACCOUNT_ID,
    state,
    editable: {
      source: state === "draft" ? "draft" : "published",
      base_revision_id: state === "draft" ? mockDraft.revision_id : mockPublished.revision_id,
      base_content_digest:
        state === "draft" ? mockDraft.content_digest : mockPublished.content_digest,
      fields: state === "draft" ? fields : publishedFields,
      avatar_url: state === "draft" ? mockDraft.avatar_url : mockPublished.avatar_url,
    },
    draft: {
      revision_id: mockDraft.revision_id,
      content_digest: mockDraft.content_digest,
      fields,
      avatar_url: mockDraft.avatar_url,
    },
    published: {
      revision_id: mockPublished.revision_id,
      content_digest: mockPublished.content_digest,
      fields: publishedFields,
      avatar_url: mockPublished.avatar_url,
      projection: {
        schema_version: 1,
        kind: "public_profile",
        account_id: FIXTURE_ACCOUNT_ID,
        display_name: mockPublished.display_name,
        bio: mockPublished.bio,
        links: [...mockPublished.links],
        avatar_url: mockPublished.avatar_url,
        author_verified: true,
      },
    },
  };
}

function unauthorized(caseId: string): MockResult {
  return { status: 401, body: errorBody("AI_STP_UNAUTHORIZED", caseId) };
}

function applyDraft(body: unknown): MockResult {
  const payload =
    body && typeof body === "object" && !Array.isArray(body)
      ? (body as Record<string, unknown>)
      : {};
  const avatar = asString(payload.avatar_asset_id);
  mockDraft = {
    revision_id: "prevision_mock_draft2",
    content_digest: `sha256:mock-draft-${Date.now().toString(16)}`,
    display_name: asString(payload.display_name),
    bio: asString(payload.bio),
    links: parseLinks(payload.links),
    avatar_asset_id: avatar,
    avatar_url: avatar ? "/brand/icon-32.png" : null,
  };
  return { status: 200, body: ownerBody("draft") };
}

function avatarReady(): MockResult {
  return {
    status: 201,
    body: {
      schema_version: 1,
      avatar_asset_id: "avatar_mock",
      state: "ready",
      public_url: "/brand/icon-32.png",
      object_key: "objects/sha256/mock",
      content_digest: "sha256:mock",
    },
  };
}

function publisherHandler(method: string, path: string): MockResult | null {
  const publisherMatch = path.match(/^\/v1\/publishers\/([^/]+)$/);
  if (method !== "GET" || !publisherMatch) return null;
  const accountId = publisherMatch[1];
  if (accountId === undefined) return null;
  const profiles = seedPublicProfiles as Record<
    string,
    (typeof seedPublicProfiles)[keyof typeof seedPublicProfiles]
  >;
  const row = profiles[accountId];
  if (row === undefined) {
    return {
      status: 200,
      body: {
        schema_version: 1,
        kind: "public_profile",
        account_id: accountId,
        display_name: null,
        bio: null,
        links: [],
        avatar_url: null,
        author_verified: false,
        empty: true,
      },
    };
  }
  return {
    status: 200,
    body: {
      schema_version: 1,
      kind: "public_profile",
      account_id: row.account_id,
      display_name:
        accountId === FIXTURE_ACCOUNT_ID ? mockPublished.display_name : row.display_name,
      bio: accountId === FIXTURE_ACCOUNT_ID ? mockPublished.bio : row.bio,
      links: accountId === FIXTURE_ACCOUNT_ID ? [...mockPublished.links] : [...row.links],
      avatar_url: accountId === FIXTURE_ACCOUNT_ID ? mockPublished.avatar_url : null,
      author_verified: row.author_verified,
    },
  };
}

export function profileHandlers(
  method: string,
  path: string,
  auth: string | null,
  body?: unknown,
): MockResult | null {
  if (method === "GET" && path === "/v1/account/public-profile") {
    return auth
      ? { status: 200, body: ownerBody("published") }
      : unauthorized("ownerProfile.unauth");
  }
  if (method === "PUT" && path === "/v1/account/public-profile/draft") {
    return auth ? applyDraft(body) : unauthorized("draft.unauth");
  }
  if (method === "GET" && path === "/v1/account/public-profile/preview") {
    if (!auth) return unauthorized("preview.unauth");
    return {
      status: 200,
      body: {
        schema_version: 1,
        preview: true,
        lifecycle: "draft",
        content_digest: mockDraft.content_digest,
        projection: {
          schema_version: 1,
          kind: "public_profile",
          account_id: FIXTURE_ACCOUNT_ID,
          display_name: mockDraft.display_name,
          bio: mockDraft.bio,
          links: mockDraft.links,
          avatar_url: mockDraft.avatar_url,
          author_verified: true,
        },
      },
    };
  }
  if (method === "POST" && path === "/v1/account/public-profile/publish") {
    if (!auth) return unauthorized("publish.unauth");
    mockPublished = { ...mockDraft, links: [...mockDraft.links] };
    return {
      status: 200,
      body: {
        schema_version: 1,
        operation_id: "operation_mock_publish",
        published: true,
        content_digest: mockPublished.content_digest,
      },
    };
  }
  if (
    method === "POST" &&
    (path === "/v1/account/public-profile/avatar" ||
      path === "/v1/account/public-profile/avatar/from-identity")
  ) {
    return auth ? avatarReady() : unauthorized("avatar.unauth");
  }
  return publisherHandler(method, path);
}
