import type { DeviceId, ETag } from "@/lib/brands";
import { apiRequest, apiRequestWithMeta } from "@/lib/api/http";

import { DEVICE_SUMMARY_FIELDS } from "./device-summary-fields";
import type {
  DeviceListResponse,
  DeviceRecord,
  DeviceRevokeResponse,
  DeviceState,
  DeviceSummary,
} from "./generated/types.gen";

export { DEVICE_SUMMARY_FIELDS };

function unwrapData(body: unknown): Record<string, unknown> {
  if (body !== null && typeof body === "object") {
    const record = body as Record<string, unknown>;
    const data = record["data"];
    if (data !== null && typeof data === "object") {
      return data as Record<string, unknown>;
    }
    return record;
  }
  return {};
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asDeviceState(value: unknown): DeviceState {
  return value === "revoked" ? "revoked" : "active";
}

function pickTimestamp(row: Record<string, unknown>, keys: readonly string[]): string {
  for (const key of keys) {
    const value = asString(row[key]);
    if (value) {
      return value;
    }
  }
  return new Date(0).toISOString();
}

function mapSummary(
  row: Record<string, unknown>,
  deviceId: string,
  last: string,
): DeviceSummary | null {
  const displayName = asString(row["display_name"]);
  const osRaw = row["operating_system"] ?? row["os"];
  if (displayName === null && typeof osRaw !== "string") {
    return null;
  }
  const operatingSystem =
    osRaw === "macos" || osRaw === "windows" || osRaw === "linux" ? osRaw : "linux";
  const architecture = row["architecture"] === "arm64" ? "arm64" : "x86_64";
  return {
    schema_version: 1,
    display_name: displayName ?? deviceId,
    operating_system: operatingSystem,
    architecture,
    detected_harnesses: [],
    toolchain_profile_version:
      asString(row["toolchain_profile_version"]) ??
      asString(row["toolset_profile_version"]) ??
      "unknown",
    summary_updated_at: asString(row["summary_updated_at"]) ?? last,
  };
}

function mapPlatformDevice(row: Record<string, unknown>): DeviceRecord | null {
  const deviceId = asString(row["device_id"]) ?? asString(row["id"]);
  if (!deviceId || !deviceId.startsWith("device_")) {
    return null;
  }
  const last = pickTimestamp(row, ["last_active_at", "last_seen_at"]);
  const registered = pickTimestamp(row, ["registered_at", "last_active_at", "last_seen_at"]);
  return {
    schema_version: 1,
    device_id: deviceId,
    state: asDeviceState(row["state"]),
    registered_at: registered,
    last_active_at: last,
    device_type: row["device_type"] === "web" ? "web" : "cli",
    approximate_location: asString(row["approximate_location"]),
    user_agent: asString(row["user_agent"]),
    etag: asString(row["etag"]) ?? 'W/"1"',
    summary: mapSummary(row, deviceId, last),
  };
}

/**
 * Normalize platform GET /v1/devices (envelope + closed summary fields) or the
 * frozen OpenAPI DeviceListResponse into the shape the web UI consumes.
 */
export function normalizeDeviceList(raw: unknown): DeviceListResponse {
  if (raw !== null && typeof raw === "object" && "items" in raw) {
    return raw as DeviceListResponse;
  }
  const data = unwrapData(raw);
  const devices = Array.isArray(data["devices"]) ? data["devices"] : [];
  const items: DeviceRecord[] = [];
  for (const entry of devices) {
    if (entry === null || typeof entry !== "object") {
      continue;
    }
    const mapped = mapPlatformDevice(entry as Record<string, unknown>);
    if (mapped) {
      items.push(mapped);
    }
  }
  return {
    schema_version: 1,
    items,
    page: { schema_version: 1, next_cursor: null, page_size: 20 },
  };
}

export async function listDevices(sessionToken: string): Promise<DeviceListResponse> {
  const raw = await apiRequest<unknown>("/v1/devices", { sessionToken });
  return normalizeDeviceList(raw);
}

export async function revokeDevice(
  sessionToken: string,
  deviceId: DeviceId,
  etag: ETag,
  idempotencyKey: string,
): Promise<{ body: DeviceRevokeResponse; operationId: string | null }> {
  const result = await apiRequestWithMeta<DeviceRevokeResponse>(`/v1/devices/${deviceId}/revoke`, {
    method: "POST",
    sessionToken,
    headers: {
      "If-Match": etag,
      "Idempotency-Key": idempotencyKey,
    },
    body: {
      schema_version: 1,
      idempotency_key: idempotencyKey,
    },
  });
  return { body: result.data, operationId: result.operationId };
}
