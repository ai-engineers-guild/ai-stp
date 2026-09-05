/* eslint-disable max-lines -- This fixture module mirrors the complete mock API route table. */
/**
 * Offline mock handlers for owner / publication / grants / reports / staff.
 * Used only by mock-transport when AI_STP_USE_MOCKS=true.
 */
import { errorBody, FIXTURE_DEVICE_ID, FIXTURE_TIMESTAMP } from "@/mocks/fixtures";
import { FIXTURE_COMPONENT_ID, ZERO_DIGEST } from "@/mocks/fixtures/catalog-ids";

export type WorkspaceMockResult = {
  status: number;
  body: unknown;
  headers?: Record<string, string>;
};

const MOCK_OP = "operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const MOCK_PLAN_ID = "plan_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const MOCK_INVITE_ID = "invite_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const MOCK_GRANT_ID = "grant_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const MOCK_CASE_ID = "case_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const MOCK_PLAN_HASH = "sha256:" + "a".repeat(64);
const MOCK_ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z";

type MockExternalProduct = {
  schema_version: 1;
  name: string;
  canonical_domain: string;
  primary_url: string;
  country_codes: string[];
};

type MockPresentation = {
  schema_version: 1;
  stable_id: string;
  bio: string;
  media: Array<{ kind: "image" | "video" | "youtube"; url: string; alt: string; caption: string }>;
};

/**
 * Process-local owner presentation store for offline e2e (serial workers).
 * Bind to globalThis so Next server-action and RSC bundles share one Map.
 */
const presentationByStableId: Map<string, MockPresentation> = (() => {
  const globalStore = globalThis as typeof globalThis & {
    __aiStpMockPresentations?: Map<string, MockPresentation>;
  };
  if (!globalStore.__aiStpMockPresentations) {
    globalStore.__aiStpMockPresentations = new Map<string, MockPresentation>();
  }
  return globalStore.__aiStpMockPresentations;
})();

const externalProductsByObject: Map<string, MockExternalProduct[]> = (() => {
  const globalStore = globalThis as typeof globalThis & {
    __aiStpMockExternalProducts?: Map<string, MockExternalProduct[]>;
  };
  if (!globalStore.__aiStpMockExternalProducts) {
    globalStore.__aiStpMockExternalProducts = new Map<string, MockExternalProduct[]>();
  }
  return globalStore.__aiStpMockExternalProducts;
})();

function defaultPresentation(stableId: string): MockPresentation {
  return {
    schema_version: 1,
    stable_id: stableId,
    bio: "Mock catalog bio",
    media: [
      {
        kind: "youtube",
        url: "dQw4w9WgXcQ",
        alt: "Demo video",
        caption: "Walkthrough",
      },
    ],
  };
}

function requireAuth(auth: string | null, caseId: string): WorkspaceMockResult | null {
  if (!auth) {
    return { status: 401, body: errorBody("AI_STP_UNAUTHORIZED", caseId) };
  }
  return null;
}

function planBody(
  planId: string,
  state: string,
  objectKind: string,
  stableId: string,
  version: string,
): Record<string, unknown> {
  return {
    schema_version: 1,
    plan_id: planId,
    state,
    object_kind: objectKind,
    stable_id: stableId,
    version,
    content_digest: ZERO_DIGEST,
    plan_hash: MOCK_PLAN_HASH,
    policy_version: "1",
    actor_id: MOCK_ACCOUNT,
    device_id: FIXTURE_DEVICE_ID,
    component_verified: false,
    expires_at: FIXTURE_TIMESTAMP,
    effects: ["publish_catalog"],
    evidence: [],
  };
}

// eslint-disable-next-line complexity, max-lines-per-function -- A flat route table keeps mock precedence explicit.
function ownerHandlers(
  method: string,
  path: string,
  auth: string | null,
  body?: unknown,
): WorkspaceMockResult | null {
  if (!path.startsWith("/v1/owner/")) {
    return null;
  }
  const unauth = requireAuth(auth, "owner.unauth");
  if (unauth) {
    return unauth;
  }
  if (method === "GET" && path === "/v1/owner/objects") {
    return {
      status: 200,
      body: {
        schema_version: 1,
        items: [
          {
            schema_version: 1,
            object_kind: "component",
            stable_id: FIXTURE_COMPONENT_ID,
            name: "Owned fixture component",
            latest_version: "1.0",
            visibility: "private",
            lifecycle_state: "draft",
            trust_lane: "experimental",
            author_verified: false,
            component_verified: false,
            updated_at: FIXTURE_TIMESTAMP,
          },
        ],
        page: { schema_version: 1, next_cursor: null, page_size: 20 },
      },
    };
  }
  const objectMatch = path.match(/^\/v1\/owner\/objects\/(component|setup)\/([^/]+)$/);
  if (method === "GET" && objectMatch) {
    return {
      status: 200,
      body: {
        schema_version: 1,
        object_kind: objectMatch[1],
        stable_id: objectMatch[2],
        name: "Owned fixture object",
        versions: [
          {
            schema_version: 1,
            version: "1.0",
            content_digest: ZERO_DIGEST,
            lifecycle_state: "draft",
            visibility: "private",
            trust_lane: "experimental",
            author_verified: false,
            component_verified: false,
            install_eligible: false,
            published_at: null,
            can_start_publication: true,
          },
        ],
      },
    };
  }
  const externalProductsMatch = path.match(
    /^\/v1\/owner\/objects\/(component|setup)\/([^/]+)\/external-products$/,
  );
  if (externalProductsMatch) {
    const key = `${externalProductsMatch[1]}:${externalProductsMatch[2]}`;
    if (method === "GET") {
      return {
        status: 200,
        body: { schema_version: 1, items: externalProductsByObject.get(key) ?? [] },
      };
    }
    if (method === "PUT") {
      const payload = body as { canonical_domains?: unknown } | undefined;
      const domains = Array.isArray(payload?.canonical_domains)
        ? payload.canonical_domains.filter((value): value is string => typeof value === "string")
        : [];
      const products = domains.map((domain) => ({
        schema_version: 1 as const,
        name: domain,
        canonical_domain: domain,
        primary_url: `https://${domain}`,
        country_codes: [],
      }));
      externalProductsByObject.set(key, products);
      return { status: 200, body: { schema_version: 1, items: products } };
    }
  }
  const versionMatch = path.match(
    /^\/v1\/owner\/objects\/(component|setup)\/([^/]+)\/versions\/([^/]+)$/,
  );
  if (method === "GET" && versionMatch) {
    return {
      status: 200,
      body: {
        schema_version: 1,
        object_kind: versionMatch[1],
        stable_id: versionMatch[2],
        name: "Owned fixture version",
        version: versionMatch[3],
        content_digest: ZERO_DIGEST,
        lifecycle_state: "draft",
        visibility: "private",
        trust_lane: "experimental",
        author_verified: false,
        component_verified: false,
        install_eligible: false,
        published_at: null,
        can_start_publication: true,
        open_publication_plan_id: "",
        evidence: [],
        description: "Mock owner version for offline UI.",
      },
    };
  }
  const startMatch = path.match(
    /^\/v1\/owner\/objects\/(component|setup)\/([^/]+)\/versions\/([^/]+)\/publication-plans$/,
  );
  if (method === "POST" && startMatch) {
    return {
      status: 201,
      body: planBody(
        MOCK_PLAN_ID,
        "ready",
        startMatch[1] ?? "component",
        startMatch[2] ?? FIXTURE_COMPONENT_ID,
        startMatch[3] ?? "1.0",
      ),
      headers: { "x-operation-id": MOCK_OP },
    };
  }
  const presentationMatch = path.match(/^\/v1\/owner\/objects\/component\/([^/]+)\/presentation$/);
  if (presentationMatch) {
    const stableId = presentationMatch[1] ?? FIXTURE_COMPONENT_ID;
    if (method === "GET") {
      return {
        status: 200,
        body: presentationByStableId.get(stableId) ?? defaultPresentation(stableId),
      };
    }
    if (method === "PUT") {
      const payload =
        body && typeof body === "object" ? (body as { bio?: unknown; media?: unknown }) : undefined;
      const bio = typeof payload?.bio === "string" ? payload.bio : "";
      const media: MockPresentation["media"] = [];
      if (Array.isArray(payload?.media)) {
        for (const raw of payload.media) {
          if (!raw || typeof raw !== "object") continue;
          const item = raw as Record<string, unknown>;
          const kind: MockPresentation["media"][number]["kind"] =
            item.kind === "video" || item.kind === "youtube" || item.kind === "image"
              ? item.kind
              : "image";
          media.push({
            kind,
            url: typeof item.url === "string" ? item.url : "",
            alt: typeof item.alt === "string" ? item.alt : "",
            caption: typeof item.caption === "string" ? item.caption : "",
          });
        }
      }
      const next: MockPresentation = {
        schema_version: 1,
        stable_id: stableId,
        bio,
        media,
      };
      presentationByStableId.set(stableId, next);
      return { status: 200, body: next };
    }
  }
  const mediaUploadMatch = path.match(
    /^\/v1\/owner\/objects\/component\/([^/]+)\/presentation\/media$/,
  );
  if (method === "POST" && mediaUploadMatch) {
    const mediaId = `media_mock_${Date.now().toString(36)}`;
    const publicUrl = `/v1/media/component/${mediaId}`;
    return {
      status: 201,
      body: {
        schema_version: 1,
        media_id: mediaId,
        kind: "image",
        public_url: publicUrl,
        content_type: "image/png",
        size_bytes: 128,
        state: "ready",
      },
    };
  }
  return null;
}

function publicationHandlers(
  method: string,
  path: string,
  auth: string | null,
): WorkspaceMockResult | null {
  if (!path.startsWith("/v1/publications/")) {
    return null;
  }
  const unauth = requireAuth(auth, "publications.unauth");
  if (unauth) {
    return unauth;
  }
  const planMatch = path.match(/^\/v1\/publications\/plans\/([^/]+)$/);
  if (method === "GET" && planMatch) {
    const body = planBody(
      planMatch[1] ?? MOCK_PLAN_ID,
      "ready",
      "component",
      FIXTURE_COMPONENT_ID,
      "1.0",
    );
    body.evidence = [{ check_id: "passport_shape", result: "passed", source: "platform" }];
    return { status: 200, body };
  }
  const confirmMatch = path.match(/^\/v1\/publications\/plans\/([^/]+)\/confirm$/);
  if (method === "POST" && confirmMatch) {
    return {
      status: 200,
      body: planBody(
        confirmMatch[1] ?? MOCK_PLAN_ID,
        "publish_planned",
        "component",
        FIXTURE_COMPONENT_ID,
        "1.0",
      ),
      headers: { "x-operation-id": MOCK_OP },
    };
  }
  return null;
}

function grantHandlers(
  method: string,
  path: string,
  auth: string | null,
): WorkspaceMockResult | null {
  if (!path.startsWith("/v1/grants")) {
    return null;
  }
  const unauth = requireAuth(auth, "grants.unauth");
  if (unauth) {
    return unauth;
  }
  if (method === "GET" && path === "/v1/grants") {
    return {
      status: 200,
      body: {
        schema_version: 1,
        invitations: [
          {
            schema_version: 1,
            invitation_id: MOCK_INVITE_ID,
            object_kind: "component",
            stable_id: FIXTURE_COMPONENT_ID,
            major: 1,
            state: "pending",
            expires_at: FIXTURE_TIMESTAMP,
            created_at: FIXTURE_TIMESTAMP,
          },
        ],
        grants: [
          {
            schema_version: 1,
            grant_id: MOCK_GRANT_ID,
            object_kind: "component",
            stable_id: FIXTURE_COMPONENT_ID,
            major: 1,
            state: "active",
            grantee_account_id: MOCK_ACCOUNT,
            owner_account_id: MOCK_ACCOUNT,
            created_at: FIXTURE_TIMESTAMP,
            revoked_at: null,
          },
        ],
      },
    };
  }
  if (method === "POST" && path === "/v1/grants/invitations") {
    return {
      status: 201,
      body: {
        schema_version: 1,
        invitation_id: MOCK_INVITE_ID,
        object_kind: "component",
        stable_id: FIXTURE_COMPONENT_ID,
        major: 1,
        state: "pending",
        expires_at: FIXTURE_TIMESTAMP,
        created_at: FIXTURE_TIMESTAMP,
      },
      headers: { "x-operation-id": MOCK_OP },
    };
  }
  if (method === "POST" && path.match(/^\/v1\/grants\/invitations\/[^/]+\/accept$/)) {
    return {
      status: 200,
      body: {
        schema_version: 1,
        grant_id: MOCK_GRANT_ID,
        object_kind: "component",
        stable_id: FIXTURE_COMPONENT_ID,
        major: 1,
        state: "active",
        grantee_account_id: MOCK_ACCOUNT,
        owner_account_id: MOCK_ACCOUNT,
        created_at: FIXTURE_TIMESTAMP,
        revoked_at: null,
      },
      headers: { "x-operation-id": MOCK_OP },
    };
  }
  if (
    method === "POST" &&
    (path.match(/^\/v1\/grants\/invitations\/[^/]+\/revoke$/) ||
      path.match(/^\/v1\/grants\/[^/]+\/revoke$/))
  ) {
    return {
      status: 200,
      body: { schema_version: 1, state: "revoked", revoked_at: FIXTURE_TIMESTAMP },
      headers: { "x-operation-id": MOCK_OP },
    };
  }
  return null;
}

// eslint-disable-next-line complexity -- Compatibility routes intentionally share one response table.
function reportHandlers(
  method: string,
  path: string,
  auth: string | null,
  body?: unknown,
): WorkspaceMockResult | null {
  if (path.startsWith("/v1/staff/")) {
    const unauth = requireAuth(auth, "staff.unauth");
    if (unauth) {
      return unauth;
    }
    if (method === "GET" && path === "/v1/staff/reports") {
      return {
        status: 200,
        body: {
          schema_version: 1,
          items: [
            {
              schema_version: 1,
              case_id: MOCK_CASE_ID,
              object_kind: "component",
              stable_id: FIXTURE_COMPONENT_ID,
              version: "1.0",
              state: "submitted",
              vulnerability: false,
              created_at: FIXTURE_TIMESTAMP,
              content_digest: ZERO_DIGEST,
            },
          ],
          page: { schema_version: 1, next_cursor: null, page_size: 20 },
        },
      };
    }
    const staffDetail = path.match(/^\/v1\/staff\/reports\/([^/]+)$/);
    if (method === "GET" && staffDetail) {
      return {
        status: 200,
        body: {
          schema_version: 1,
          case_id: staffDetail[1],
          object_kind: "component",
          stable_id: FIXTURE_COMPONENT_ID,
          version: "1.0",
          state: "submitted",
          vulnerability: false,
          created_at: FIXTURE_TIMESTAMP,
          content_digest: ZERO_DIGEST,
          error_code: "",
          harness_id: "",
        },
      };
    }
    if (method === "POST" && path.match(/^\/v1\/staff\/reports\/[^/]+\/triage$/)) {
      return {
        status: 200,
        body: {
          schema_version: 1,
          case_id: MOCK_CASE_ID,
          object_kind: "component",
          stable_id: FIXTURE_COMPONENT_ID,
          version: "1.0",
          state: "triaged",
          vulnerability: false,
          created_at: FIXTURE_TIMESTAMP,
        },
        headers: { "x-operation-id": MOCK_OP },
      };
    }
    if (method === "POST" && path === "/v1/staff/versions/lifecycle") {
      return {
        status: 200,
        body: { schema_version: 1, state: "applied" },
        headers: { "x-operation-id": MOCK_OP },
      };
    }
    return null;
  }

  if (!path.startsWith("/v1/reports") && !path.startsWith("/v1/requests")) {
    return null;
  }
  const unauth = requireAuth(auth, "reports.unauth");
  if (unauth) {
    return unauth;
  }
  if (method === "GET" && path.startsWith("/v1/requests/") && path !== "/v1/requests") {
    return {
      status: 200,
      body: {
        schema_version: 1,
        case_id: MOCK_CASE_ID,
        topic: "object_report",
        object_kind: "component",
        stable_id: FIXTURE_COMPONENT_ID,
        version: "1.0",
        state: "submitted",
        vulnerability: false,
        locale: "en",
        created_at: FIXTURE_TIMESTAMP,
      },
    };
  }
  if (method === "GET" && (path === "/v1/reports" || path === "/v1/requests")) {
    return {
      status: 200,
      body: {
        schema_version: 1,
        items: [
          {
            schema_version: 1,
            case_id: MOCK_CASE_ID,
            object_kind: "component",
            stable_id: FIXTURE_COMPONENT_ID,
            version: "1.0",
            state: "submitted",
            vulnerability: false,
            created_at: FIXTURE_TIMESTAMP,
          },
        ],
      },
    };
  }
  if (method === "POST" && (path === "/v1/reports" || path === "/v1/requests")) {
    const topic =
      body && typeof body === "object" && "topic" in body && typeof body.topic === "string"
        ? body.topic
        : "object_report";
    return {
      status: 201,
      body: {
        schema_version: 1,
        case_id: MOCK_CASE_ID,
        object_kind: "component",
        stable_id: FIXTURE_COMPONENT_ID,
        version: "1.0",
        state: "submitted",
        vulnerability: false,
        topic,
        created_at: FIXTURE_TIMESTAMP,
      },
      headers: { "x-operation-id": MOCK_OP },
    };
  }
  return null;
}

/** Route owner/publication/grants/reports/staff mock traffic. */
export function workspaceHandlers(
  method: string,
  path: string,
  auth: string | null,
  body?: unknown,
): WorkspaceMockResult | null {
  return (
    ownerHandlers(method, path, auth, body) ??
    publicationHandlers(method, path, auth) ??
    grantHandlers(method, path, auth) ??
    reportHandlers(method, path, auth, body)
  );
}
