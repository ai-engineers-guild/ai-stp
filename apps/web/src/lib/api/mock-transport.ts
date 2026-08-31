/* eslint-disable max-lines -- One exhaustive in-process mirror of the HTTP mock surface. */
/**
 * In-process mock transport for server reads when AI_STP_USE_MOCKS=true.
 * Serves the same seed/fixture shapes as MSW handlers so RSC and tests share one corpus.
 */
import {
  accountProfile,
  deviceList,
  errorBody,
  FIXTURE_DEVICE_ID,
  getComponentDetail,
  getSetupDetail,
  FIXTURE_TIMESTAMP,
} from "@/mocks/fixtures";
import { filterComponentSummaries, filterSetupSummaries } from "@/mocks/filter-catalog";
import { componentVersionResponse, setupVersionResponse } from "@/mocks/passport-fixtures";

import { mapHttpError, ApiError } from "./errors";
import { profileHandlers } from "./mock-profile";
import { workspaceHandlers } from "./mock-workspace";

type MockResult = { status: number; body: unknown; headers?: Record<string, string> };

const CATALOG_COMPONENT_KEYS = new Set([
  "schema_version",
  "q",
  "tags",
  "harness_id",
  "component_type",
  "support_tier",
  "support_state",
  "cursor",
  "page_size",
  "page",
  "include_experimental",
  "harness_ids",
  "component_types",
  "authors",
  "verified_only",
  "sort",
  "sort_direction",
  "service_domain",
  "country_code",
  "service_domains",
  "country_codes",
  "updated_from",
  "updated_to",
]);

const CATALOG_SETUP_KEYS = new Set([
  "schema_version",
  "q",
  "tags",
  "harness_id",
  "support_tier",
  "support_state",
  "cursor",
  "page_size",
  "page",
  "include_experimental",
  "harness_ids",
  "authors",
  "verified_only",
  "sort",
  "sort_direction",
  "service_domain",
  "country_code",
  "service_domains",
  "country_codes",
  "updated_from",
  "updated_to",
]);

function notFound(caseId: string): MockResult {
  return { status: 404, body: errorBody("AI_STP_NOT_FOUND", caseId) };
}

function validationError(caseId: string, fields: string): MockResult {
  const body = errorBody("AI_STP_VALIDATION_ERROR", caseId);
  body.error.details = { fields };
  return { status: 400, body };
}

function readAuth(headers?: HeadersInit): string | null {
  if (headers instanceof Headers) {
    return headers.get("authorization");
  }
  if (headers && typeof headers === "object" && !Array.isArray(headers)) {
    return headers["Authorization"] ?? headers["authorization"] ?? null;
  }
  return null;
}

function rejectUnknown(query: URLSearchParams | undefined, allowed: Set<string>): string[] {
  if (!query) {
    return [];
  }
  const unknown = new Set<string>();
  for (const key of query.keys()) {
    if (!allowed.has(key)) {
      unknown.add(key);
    }
  }
  return [...unknown].sort();
}

function listBody(
  experimental: unknown[],
  nextCursor: string | null = null,
  pageSize = 20,
  pageNumber?: number,
  totalItems?: number,
): MockResult {
  return {
    status: 200,
    body: {
      schema_version: 1,
      items: [],
      experimental,
      page:
        pageNumber === undefined
          ? { schema_version: 1, mode: "cursor", next_cursor: nextCursor, page_size: pageSize }
          : {
              schema_version: 1,
              mode: "page",
              next_cursor: null,
              page_size: pageSize,
              page_number: pageNumber,
              total_items: totalItems ?? experimental.length,
              total_pages: Math.ceil((totalItems ?? experimental.length) / pageSize),
              previous_page: pageNumber > 1 ? pageNumber - 1 : null,
              next_page:
                pageNumber * pageSize < (totalItems ?? experimental.length) ? pageNumber + 1 : null,
            },
    },
  };
}

function paginate<T>(
  all: T[],
  cursor: string | null,
  pageSize: number,
): { page: T[]; next: string | null } {
  const start = cursor ? Number.parseInt(cursor, 10) : 0;
  if (Number.isNaN(start) || start < 0) {
    return { page: [], next: null };
  }
  const page = all.slice(start, start + pageSize);
  const nextIndex = start + pageSize;
  return {
    page,
    next: nextIndex < all.length ? String(nextIndex) : null,
  };
}

function paginatedList<T>(
  items: T[],
  query: URLSearchParams | undefined,
  cursor: string | null,
  pageSize: number,
): MockResult {
  const pageNumberRaw = query?.get("page");
  if (pageNumberRaw) {
    const pageNumber = Number.parseInt(pageNumberRaw, 10) || 1;
    const start = (pageNumber - 1) * pageSize;
    return listBody(items.slice(start, start + pageSize), null, pageSize, pageNumber, items.length);
  }
  const { page, next } = paginate(items, cursor, pageSize);
  return listBody(page, next, pageSize);
}

/** Test-only sentinel: offline e2e forces AI_STP_UNAVAILABLE without a real backend. */
const FORCE_UNAVAILABLE_Q = "__ai_stp_force_unavailable__";

function searchComponents(query?: URLSearchParams): MockResult {
  const unknown = rejectUnknown(query, CATALOG_COMPONENT_KEYS);
  if (unknown.length > 0) {
    return validationError("searchComponents.unknownParam", unknown.join(","));
  }
  const includeExperimental =
    query?.get("include_experimental") === "true" || query?.get("include_experimental") === "1";
  const q = query?.get("q");
  if (q === FORCE_UNAVAILABLE_Q) {
    return { status: 503, body: errorBody("AI_STP_UNAVAILABLE", "catalog.unavailable") };
  }
  const range = readUpdatedRange(query, "searchComponents.updatedRange");
  if ("status" in range) return range;
  const tags = query?.getAll("tags") ?? [];
  const harnessId = query?.get("harness_id");
  const componentType = query?.get("component_type");
  const supportTier = query?.get("support_tier") as "primary" | "beta" | null;
  const supportState = query?.get("support_state") as
    "verified" | "stale" | "missing" | "not_verified" | null;
  const pageSize = Number.parseInt(query?.get("page_size") ?? "25", 10) || 25;
  const cursor = query?.get("cursor") ?? null;
  const filtered = filterComponentSummaries({
    ...(q ? { q } : {}),
    tags,
    ...(harnessId ? { harnessId } : {}),
    ...(componentType ? { componentType } : {}),
    ...(supportTier ? { supportTier } : {}),
    ...(supportState ? { supportState } : {}),
    ...range,
    includeExperimental,
  });
  return paginatedList(filtered.experimental, query, cursor, pageSize);
}

function searchSetups(query?: URLSearchParams): MockResult {
  const unknown = rejectUnknown(query, CATALOG_SETUP_KEYS);
  if (unknown.length > 0) {
    return validationError("searchSetups.unknownParam", unknown.join(","));
  }
  const includeExperimental =
    query?.get("include_experimental") === "true" || query?.get("include_experimental") === "1";
  const q = query?.get("q");
  if (q === FORCE_UNAVAILABLE_Q) {
    return { status: 503, body: errorBody("AI_STP_UNAVAILABLE", "catalog.unavailable") };
  }
  const range = readUpdatedRange(query, "searchSetups.updatedRange");
  if ("status" in range) return range;
  const tags = query?.getAll("tags") ?? [];
  const harnessId = query?.get("harness_id");
  const supportTier = query?.get("support_tier") as "primary" | "beta" | null;
  const supportState = query?.get("support_state") as
    "verified" | "stale" | "missing" | "not_verified" | null;
  const pageSize = Number.parseInt(query?.get("page_size") ?? "25", 10) || 25;
  const cursor = query?.get("cursor") ?? null;
  const filtered = filterSetupSummaries({
    ...(q ? { q } : {}),
    tags,
    ...(harnessId ? { harnessId } : {}),
    ...(supportTier ? { supportTier } : {}),
    ...(supportState ? { supportState } : {}),
    ...range,
    includeExperimental,
  });
  return paginatedList(filtered.experimental, query, cursor, pageSize);
}

function readUpdatedRange(
  query: URLSearchParams | undefined,
  caseId: string,
): { updatedFrom?: string; updatedTo?: string } | MockResult {
  const updatedFrom = query?.get("updated_from") ?? undefined;
  const updatedTo = query?.get("updated_to") ?? undefined;
  if (updatedFrom && updatedTo && updatedFrom > updatedTo) {
    return validationError(caseId, "updated_from,updated_to");
  }
  return {
    ...(updatedFrom ? { updatedFrom } : {}),
    ...(updatedTo ? { updatedTo } : {}),
  };
}

const MOCK_REVISION = `revision_${"a".repeat(64)}`;
const MOCK_DIGEST = `sha256:${"b".repeat(64)}`;
const MOCK_ETAG = `sha256:${"c".repeat(64)}`;

type MockContent = {
  type: "article";
  slug: string;
  locale: "en" | "ru";
  title: string;
  description: string;
  published_at: string;
  tags: string[];
  body: string;
};

const MOCK_CONTENT: MockContent[] = [
  {
    type: "article",
    slug: "safe-setup",
    locale: "en",
    title: "Build a setup without hiding its trust boundary",
    description: "A practical guide to provenance, exact versions and explicit consent in ai_stp.",
    published_at: "2026-08-12",
    tags: ["setup", "trust"],
    body: "An ai_stp setup pins exact component versions and keeps provenance visible.",
  },
  {
    type: "article",
    slug: "safe-setup",
    locale: "ru",
    title: "Как собрать сетап, не скрывая границу доверия",
    description:
      "Практическое руководство о происхождении, точных версиях и явном согласии в ai_stp.",
    published_at: "2026-08-12",
    tags: ["setup", "trust"],
    body: "Сетап ai_stp закрепляет точные версии компонентов и сохраняет видимым их происхождение.",
  },
];

function contentHandlers(method: string, path: string, query?: URLSearchParams): MockResult | null {
  if (method !== "GET") return null;
  const locale = query?.get("locale");
  if (path === "/v1/content") {
    if (locale !== "en" && locale !== "ru") {
      return validationError("listContent.locale", "locale");
    }
    const items = MOCK_CONTENT.filter((entry) => entry.locale === locale).map((entry) => ({
      schema_version: 1 as const,
      type: entry.type,
      slug: entry.slug,
      locale: entry.locale,
      title: entry.title,
      description: entry.description,
      published_at: entry.published_at,
      tags: entry.tags,
      revision_id: MOCK_REVISION,
      content_digest: MOCK_DIGEST,
      source_kind: "repository" as const,
    }));
    return {
      status: 200,
      body: { schema_version: 1, etag: MOCK_ETAG, items },
    };
  }
  const detail = path.match(/^\/v1\/content\/([^/]+)\/([^/]+)$/);
  if (!detail) return null;
  if (detail[1] === "repository") return null;
  if (locale !== "en" && locale !== "ru") {
    return validationError("readContent.locale", "locale");
  }
  const entry = MOCK_CONTENT.find(
    (item) => item.type === detail[1] && item.slug === detail[2] && item.locale === locale,
  );
  if (!entry) return notFound("readContent.unknown");
  return {
    status: 200,
    body: {
      schema_version: 1,
      type: entry.type,
      slug: entry.slug,
      locale: entry.locale,
      title: entry.title,
      description: entry.description,
      published_at: entry.published_at,
      tags: entry.tags,
      revision_id: MOCK_REVISION,
      content_digest: MOCK_DIGEST,
      source_kind: "repository",
      body: entry.body,
      source_ref: "a".repeat(40),
      source_path: `docs-user-facing/content/${entry.locale}/article-${entry.slug}.md`,
    },
  };
}

function catalogHandlers(method: string, path: string, query?: URLSearchParams): MockResult | null {
  if (method !== "GET") {
    return null;
  }
  if (path === "/v1/catalog/components") {
    return searchComponents(query);
  }
  if (path === "/v1/catalog/setups") {
    return searchSetups(query);
  }
  const componentMatch = path.match(/^\/v1\/catalog\/components\/([^/]+)$/);
  if (componentMatch) {
    const detail = getComponentDetail(componentMatch[1] ?? "");
    return detail ? { status: 200, body: detail } : notFound("readComponent.unknownObject");
  }
  const setupMatch = path.match(/^\/v1\/catalog\/setups\/([^/]+)$/);
  if (setupMatch) {
    const detail = getSetupDetail(setupMatch[1] ?? "");
    return detail ? { status: 200, body: detail } : notFound("readSetup.unknownObject");
  }
  const componentVersionMatch = path.match(
    /^\/v1\/catalog\/components\/([^/]+)\/versions\/([^/]+)$/,
  );
  if (componentVersionMatch) {
    const body = componentVersionResponse(
      componentVersionMatch[1] ?? "",
      componentVersionMatch[2] ?? "",
    );
    return body ? { status: 200, body } : notFound("readComponentVersion.unknown");
  }
  const setupVersionMatch = path.match(/^\/v1\/catalog\/setups\/([^/]+)\/versions\/([^/]+)$/);
  if (setupVersionMatch) {
    const body = setupVersionResponse(setupVersionMatch[1] ?? "", setupVersionMatch[2] ?? "");
    return body ? { status: 200, body } : notFound("readSetupVersion.unknown");
  }
  if (path === "/v1/catalog/services") {
    return { status: 200, body: { schema_version: 1, items: [] } };
  }
  const serviceMatch = path.match(/^\/v1\/catalog\/services\/([^/]+)$/);
  if (serviceMatch) {
    return notFound("readExternalProduct.unknown");
  }
  const countryMatch = path.match(/^\/v1\/catalog\/countries\/([^/]+)$/);
  if (countryMatch) {
    return notFound("readCountry.unknown");
  }
  return null;
}

function reactionHandler(method: string, path: string): MockResult | null {
  if (!/^(?:PUT|DELETE)$/.test(method)) return null;
  if (!/^\/v1\/account\/catalog-reactions\/(?:component|setup)\/[^/]+$/.test(path)) return null;
  const liked = method === "PUT";
  return { status: 200, body: { schema_version: 1, liked, likes_count: liked ? 1 : 0 } };
}

function privacyHandlers(
  method: string,
  path: string,
  auth: string | null,
  body?: unknown,
): MockResult | null {
  if (method !== "PUT" || path !== "/v1/account/privacy") return null;
  if (!auth) {
    return { status: 401, body: errorBody("AI_STP_UNAUTHORIZED", "updatePrivacy.unauth") };
  }
  const values = body as {
    show_profile_publicly?: unknown;
    allow_publisher_listing?: unknown;
  };
  if (
    typeof values.show_profile_publicly !== "boolean" ||
    typeof values.allow_publisher_listing !== "boolean"
  ) {
    return { status: 422, body: errorBody("AI_STP_VALIDATION_ERROR", "updatePrivacy.body") };
  }
  return {
    status: 200,
    body: {
      ...accountProfile,
      show_profile_publicly: values.show_profile_publicly,
      allow_publisher_listing: values.allow_publisher_listing,
    },
  };
}

function identityHandlers(
  method: string,
  path: string,
  auth: string | null,
  headers?: HeadersInit,
  body?: unknown,
): MockResult | null {
  if (method === "GET" && path === "/v1/account") {
    if (!auth) {
      return { status: 401, body: errorBody("AI_STP_UNAUTHORIZED", "readAccount.unauth") };
    }
    return { status: 200, body: accountProfile };
  }
  const privacy = privacyHandlers(method, path, auth, body);
  if (privacy) return privacy;
  const profile = profileHandlers(method, path, auth, body);
  if (profile) {
    return profile;
  }
  if (method === "GET" && path === "/v1/devices") {
    if (!auth) {
      return { status: 401, body: errorBody("AI_STP_UNAUTHORIZED", "listDevices.unauth") };
    }
    return { status: 200, body: deviceList };
  }
  const revokeMatch = path.match(/^\/v1\/devices\/([^/]+)\/revoke$/);
  if (method === "POST" && revokeMatch) {
    if (!auth) {
      return { status: 401, body: errorBody("AI_STP_UNAUTHORIZED", "revokeDevice.unauth") };
    }
    const ifMatch = new Headers(headers).get("if-match");
    const deviceId = revokeMatch[1];
    if (deviceId === FIXTURE_DEVICE_ID && ifMatch !== 'W/"7"') {
      return {
        status: 412,
        body: errorBody("AI_STP_PRECONDITION_FAILED", "revokeDevice.stalePrecondition"),
      };
    }
    const device = deviceList.items.find((item) => item.device_id === deviceId);
    if (!device) {
      return notFound("revokeDevice.unknown");
    }
    return {
      status: 200,
      body: {
        schema_version: 1,
        device: { ...device, state: "revoked", etag: 'W/"8"' },
        revoked_at: FIXTURE_TIMESTAMP,
      },
      headers: { "x-operation-id": "operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z" },
    };
  }
  return null;
}

function deviceApprovalHandler(
  method: string,
  path: string,
  auth: string | null,
  body: unknown,
): MockResult | null {
  if (method !== "POST" || path !== "/v1/auth/device/approve") {
    return null;
  }
  if (!auth) {
    return { status: 401, body: errorBody("AI_STP_UNAUTHORIZED", "approveDevice.unauth") };
  }
  const userCode =
    body !== null && typeof body === "object" && "user_code" in body
      ? (body as { user_code?: unknown }).user_code
      : null;
  if (typeof userCode !== "string" || !userCode.trim()) {
    return { status: 422, body: errorBody("AI_STP_VALIDATION_ERROR", "approveDevice.code") };
  }
  return { status: 200, body: { status: "approved" } };
}

function complaintHandler(method: string, path: string, body: unknown): MockResult | null {
  if (method !== "POST" || path !== "/v1/complaints") {
    return null;
  }
  if (body === null || typeof body !== "object") {
    return { status: 422, body: errorBody("AI_STP_VALIDATION_ERROR", "createComplaint.body") };
  }
  const values = body as Record<string, unknown>;
  const required = ["target_kind", "target", "sender_name", "reply_email", "subject", "message"];
  if (required.some((key) => typeof values[key] !== "string" || !values[key].trim())) {
    return { status: 422, body: errorBody("AI_STP_VALIDATION_ERROR", "createComplaint.body") };
  }
  return {
    status: 201,
    body: {
      schema_version: 1,
      complaint_id: "complaint_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
      accepted: true,
      created_at: FIXTURE_TIMESTAMP,
    },
  };
}

function legalDocumentHandler(
  method: string,
  path: string,
  query?: URLSearchParams,
): MockResult | null {
  if (method !== "GET") return null;
  const match = path.match(
    /^\/v1\/documents\/(privacy|cookies|service-rules|personal-data-consent|licensing)$/,
  );
  if (!match) return null;
  const slug = match[1] ?? "";
  const locale = query?.get("locale") === "ru" ? "ru" : "en";
  const titles: Record<string, Record<string, string>> = {
    en: {
      privacy: "Privacy notice",
      cookies: "Cookie Policy",
      "service-rules": "Service rules",
      "personal-data-consent": "Personal data consent",
      licensing: "Licensing",
    },
    ru: {
      privacy: "Политика конфиденциальности",
      cookies: "Уведомление о cookie",
      "service-rules": "Правила сервиса",
      "personal-data-consent": "Согласие на обработку персональных данных",
      licensing: "Лицензирование",
    },
  };
  return {
    status: 200,
    body: {
      schema_version: 1,
      slug,
      revision_id: `drev_mock_${slug}_${locale}`,
      locale,
      title: titles[locale]?.[slug] ?? slug,
      policy_version: "1.0",
      effective_at: "2026-09-01T00:00:00Z",
      source_ref: "a".repeat(40),
      source_path: `docs-user-facing/legal/${locale}/${slug}/1.0/document.md`,
      html: "<p>Versioned legal document.</p>",
    },
  };
}

function parseMockBody(raw: string | undefined): unknown {
  if (!raw) {
    return undefined;
  }
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return undefined;
  }
}

export function mockFetch(
  method: string,
  path: string,
  init?: {
    query?: URLSearchParams;
    headers?: HeadersInit;
    body?: string;
  },
): MockResult {
  const auth = readAuth(init?.headers);
  const body = parseMockBody(init?.body);
  const complaint = complaintHandler(method, path, body);
  if (complaint) return complaint;
  const legal = legalDocumentHandler(method, path, init?.query);
  if (legal) return legal;
  const reaction = reactionHandler(method, path);
  if (reaction) return reaction;
  const content = contentHandlers(method, path, init?.query);
  if (content) {
    return content;
  }
  const catalog = catalogHandlers(method, path, init?.query);
  if (catalog) {
    return catalog;
  }
  const deviceApproval = deviceApprovalHandler(method, path, auth, body);
  if (deviceApproval) {
    return deviceApproval;
  }
  const identity = identityHandlers(method, path, auth, init?.headers, body);
  if (identity) {
    return identity;
  }
  const workspace = workspaceHandlers(method, path, auth, body);
  if (workspace) {
    return workspace;
  }
  throw new ApiError({
    code: "AI_STP_NOT_FOUND",
    message: `no mock for ${method} ${path}`,
    status: 404,
  });
}

export function mockResultToData<T>(result: MockResult): T {
  if (result.status < 200 || result.status >= 300) {
    throw mapHttpError(result.status, result.body, new Headers(result.headers));
  }
  return result.body as T;
}
