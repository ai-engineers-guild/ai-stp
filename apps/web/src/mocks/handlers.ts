import { http, HttpResponse } from "msw";

import { filterComponentSummaries, filterSetupSummaries } from "./filter-catalog";
import {
  accountProfile,
  deviceList,
  errorBody,
  FIXTURE_DEVICE_ID,
  getComponentDetail,
  getSetupDetail,
  FIXTURE_TIMESTAMP,
} from "./fixtures";
import { componentVersionResponse, setupVersionResponse } from "./passport-fixtures";

function api(path: string): string {
  return `*/v1${path}`;
}

/**
 * MSW handlers over #71 + first-party seed fixtures (mock-first for #82/#83).
 */
export const handlers = [
  http.get(api("/catalog/components"), ({ request }) => {
    const url = new URL(request.url);
    const unknown = [...url.searchParams.keys()].filter(
      (key) =>
        ![
          "schema_version",
          "q",
          "tags",
          "harness_id",
          "component_type",
          "harness_ids",
          "component_types",
          "authors",
          "verified_only",
          "sort",
          "sort_direction",
          "support_tier",
          "support_state",
          "cursor",
          "page_size",
          "page",
          "include_experimental",
          "service_domain",
          "country_code",
          "service_domains",
          "country_codes",
          "updated_from",
          "updated_to",
        ].includes(key),
    );
    if (unknown.length > 0) {
      return HttpResponse.json(
        errorBody("AI_STP_VALIDATION_ERROR", "searchComponents.unknownParam"),
        { status: 400 },
      );
    }
    const includeExperimental =
      url.searchParams.get("include_experimental") === "true" ||
      url.searchParams.get("include_experimental") === "1";
    const q = url.searchParams.get("q");
    const harnessId = url.searchParams.get("harness_id");
    const componentType = url.searchParams.get("component_type");
    const supportTier = url.searchParams.get("support_tier") as "primary" | "beta" | null;
    const supportState = url.searchParams.get("support_state") as
      "verified" | "stale" | "missing" | "not_verified" | null;
    const updatedFrom = url.searchParams.get("updated_from");
    const updatedTo = url.searchParams.get("updated_to");
    const result = filterComponentSummaries({
      ...(q ? { q } : {}),
      tags: url.searchParams.getAll("tags"),
      ...(harnessId ? { harnessId } : {}),
      ...(componentType ? { componentType } : {}),
      ...(supportTier ? { supportTier } : {}),
      ...(supportState ? { supportState } : {}),
      ...(updatedFrom ? { updatedFrom } : {}),
      ...(updatedTo ? { updatedTo } : {}),
      includeExperimental,
    });
    const all = [...result.items, ...result.experimental];
    const pageNumber = Number(url.searchParams.get("page") ?? "1");
    const pageSize = Number(url.searchParams.get("page_size") ?? "20");
    const start = (pageNumber - 1) * pageSize;
    const pageItems = all.slice(start, start + pageSize);
    return HttpResponse.json({
      schema_version: 1,
      items: [],
      experimental: pageItems,
      page: {
        schema_version: 1,
        mode: "page",
        next_cursor: null,
        page_size: pageSize,
        page_number: pageNumber,
        total_items: all.length,
        total_pages: Math.ceil(all.length / pageSize),
        previous_page: pageNumber > 1 ? pageNumber - 1 : null,
        next_page: start + pageSize < all.length ? pageNumber + 1 : null,
      },
    });
  }),

  http.get(api("/catalog/setups"), ({ request }) => {
    const url = new URL(request.url);
    const includeExperimental =
      url.searchParams.get("include_experimental") === "true" ||
      url.searchParams.get("include_experimental") === "1";
    const q = url.searchParams.get("q");
    const harnessId = url.searchParams.get("harness_id");
    const supportTier = url.searchParams.get("support_tier") as "primary" | "beta" | null;
    const supportState = url.searchParams.get("support_state") as
      "verified" | "stale" | "missing" | "not_verified" | null;
    const updatedFrom = url.searchParams.get("updated_from");
    const updatedTo = url.searchParams.get("updated_to");
    const result = filterSetupSummaries({
      ...(q ? { q } : {}),
      tags: url.searchParams.getAll("tags"),
      ...(harnessId ? { harnessId } : {}),
      ...(supportTier ? { supportTier } : {}),
      ...(supportState ? { supportState } : {}),
      ...(updatedFrom ? { updatedFrom } : {}),
      ...(updatedTo ? { updatedTo } : {}),
      includeExperimental,
    });
    const all = [...result.items, ...result.experimental];
    const pageNumber = Number(url.searchParams.get("page") ?? "1");
    const pageSize = Number(url.searchParams.get("page_size") ?? "20");
    const start = (pageNumber - 1) * pageSize;
    return HttpResponse.json({
      schema_version: 1,
      items: [],
      experimental: all.slice(start, start + pageSize),
      page: {
        schema_version: 1,
        mode: "page",
        next_cursor: null,
        page_size: pageSize,
        page_number: pageNumber,
        total_items: all.length,
        total_pages: Math.ceil(all.length / pageSize),
        previous_page: pageNumber > 1 ? pageNumber - 1 : null,
        next_page: start + pageSize < all.length ? pageNumber + 1 : null,
      },
    });
  }),

  http.get(api("/catalog/components/:stableId"), ({ params }) => {
    const detail = getComponentDetail(String(params["stableId"]));
    if (!detail) {
      return HttpResponse.json(errorBody("AI_STP_NOT_FOUND", "readComponent.unknownObject"), {
        status: 404,
      });
    }
    return HttpResponse.json(detail);
  }),

  http.get(api("/catalog/setups/:stableId"), ({ params }) => {
    const detail = getSetupDetail(String(params["stableId"]));
    if (!detail) {
      return HttpResponse.json(errorBody("AI_STP_NOT_FOUND", "readSetup.unknownObject"), {
        status: 404,
      });
    }
    return HttpResponse.json(detail);
  }),

  http.get(api("/catalog/components/:stableId/versions/:version"), ({ params }) => {
    const body = componentVersionResponse(
      String(params["stableId"]),
      String(params["version"] ?? "1.0"),
    );
    if (!body) {
      return HttpResponse.json(errorBody("AI_STP_NOT_FOUND", "readComponentVersion.unknown"), {
        status: 404,
      });
    }
    return HttpResponse.json(body);
  }),

  http.get(api("/catalog/setups/:stableId/versions/:version"), ({ params }) => {
    const body = setupVersionResponse(
      String(params["stableId"]),
      String(params["version"] ?? "1.0"),
    );
    if (!body) {
      return HttpResponse.json(errorBody("AI_STP_NOT_FOUND", "readSetupVersion.unknown"), {
        status: 404,
      });
    }
    return HttpResponse.json(body);
  }),

  http.get(api("/account"), ({ request }) => {
    const auth = request.headers.get("authorization");
    if (!auth) {
      return HttpResponse.json(errorBody("AI_STP_UNAUTHORIZED", "readAccount.unauth"), {
        status: 401,
      });
    }
    return HttpResponse.json(accountProfile);
  }),

  http.delete(api("/account/identities/:provider"), ({ request, params }) => {
    const auth = request.headers.get("authorization");
    if (!auth) {
      return HttpResponse.json(errorBody("AI_STP_UNAUTHORIZED", "unlinkIdentity.unauth"), {
        status: 401,
      });
    }
    const provider = params["provider"];
    if (provider !== "google" && provider !== "github") {
      return HttpResponse.json(errorBody("AI_STP_VALIDATION_ERROR", "unlinkIdentity.provider"), {
        status: 400,
      });
    }
    const remaining = accountProfile.identities.filter((item) => item.provider !== provider);
    if (remaining.length === accountProfile.identities.length) {
      return HttpResponse.json(errorBody("AI_STP_NOT_FOUND", "unlinkIdentity.missing"), {
        status: 404,
      });
    }
    if (remaining.length < 1) {
      return HttpResponse.json(errorBody("AI_STP_VALIDATION_ERROR", "unlinkIdentity.last"), {
        status: 400,
      });
    }
    return HttpResponse.json({
      ...accountProfile,
      identities: remaining,
    });
  }),

  http.get(api("/devices"), ({ request }) => {
    const auth = request.headers.get("authorization");
    if (!auth) {
      return HttpResponse.json(errorBody("AI_STP_UNAUTHORIZED", "listDevices.unauth"), {
        status: 401,
      });
    }
    return HttpResponse.json(deviceList);
  }),

  http.post(api("/devices/:deviceId/revoke"), ({ request, params }) => {
    const auth = request.headers.get("authorization");
    if (!auth) {
      return HttpResponse.json(errorBody("AI_STP_UNAUTHORIZED", "revokeDevice.unauth"), {
        status: 401,
      });
    }
    const ifMatch = request.headers.get("if-match");
    if (ifMatch !== 'W/"7"' && params["deviceId"] === FIXTURE_DEVICE_ID) {
      return HttpResponse.json(
        errorBody("AI_STP_PRECONDITION_FAILED", "revokeDevice.stalePrecondition"),
        { status: 412 },
      );
    }
    const device = deviceList.items.find((item) => item.device_id === params["deviceId"]);
    if (!device) {
      return HttpResponse.json(errorBody("AI_STP_NOT_FOUND", "revokeDevice.unknown"), {
        status: 404,
      });
    }
    return HttpResponse.json(
      {
        schema_version: 1,
        device: {
          ...device,
          state: "revoked",
          etag: 'W/"8"',
        },
        revoked_at: FIXTURE_TIMESTAMP,
      },
      {
        status: 200,
        headers: {
          "X-Operation-Id": "operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        },
      },
    );
  }),

  http.get(api("/auth/:provider/callback"), ({ params }) => {
    const provider = params["provider"];
    if (provider !== "google" && provider !== "github") {
      return HttpResponse.json(errorBody("AI_STP_VALIDATION_ERROR", "oauth.unknownProvider"), {
        status: 400,
      });
    }
    return HttpResponse.json({
      schema_version: 1,
      provider,
      status: "linked",
      account_id: accountProfile.account_id,
      completed_at: FIXTURE_TIMESTAMP,
    });
  }),

  http.post(api("/complaints"), async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const required = ["target_kind", "target", "sender_name", "reply_email", "subject", "message"];
    if (required.some((key) => typeof body[key] !== "string" || !body[key].trim())) {
      return HttpResponse.json(errorBody("AI_STP_VALIDATION_ERROR", "createComplaint.body"), {
        status: 422,
      });
    }
    return HttpResponse.json(
      {
        schema_version: 1,
        complaint_id: "complaint_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        accepted: true,
        created_at: FIXTURE_TIMESTAMP,
      },
      { status: 201 },
    );
  }),
];
