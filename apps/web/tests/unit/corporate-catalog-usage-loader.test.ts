import { beforeEach, describe, expect, it, vi } from "vitest";

const { request } = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("@/lib/api/http", () => ({ privateApiRequest: request }));

import { ApiError } from "@/lib/api/errors";
import { asComponentId } from "@/lib/brands";
import { readCorporateCatalogUsage } from "@/lib/api/corporate-catalog-ownership";
import type { CorporateCatalogUsage } from "@/lib/api/generated/types.gen";

const organizationId = "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const stableId = asComponentId("component_01JQZK7B8N4M6P2R9T5V0X3Y7Z");

const usageRow = (index: number): CorporateCatalogUsage => ({
  assignment_id: `catalog_assignment_01JQZK7B8N4M6P2R9T5V0X${String(index % 10)}`,
  object_kind: "component",
  organization_id: organizationId,
  schema_version: 1,
  selector: "latest",
  source: "effective",
  source_team_id: null,
  stable_id: stableId,
  subject_id: `account_01JQZK7B8N4M6P2R9T5V0X${String(index % 10)}`,
  subject_kind: "employee",
  subject_name: `Member ${index}`,
  version: null,
});

const page = (total: number, offset: number, limit: number) => ({
  schema_version: 1 as const,
  total,
  items: Array.from({ length: Math.max(0, Math.min(limit, total - offset)) }, (_, i) =>
    usageRow(offset + i),
  ),
});

beforeEach(() => vi.clearAllMocks());

describe("readCorporateCatalogUsage (#333)", () => {
  it.each([0, 1])("returns a complete set at %i rows in one request", async (total) => {
    request.mockImplementation((_path, { query }) =>
      Promise.resolve(page(total, query.offset ?? 0, query.limit)),
    );
    const result = await readCorporateCatalogUsage(
      "token",
      organizationId,
      "component",
      stableId,
    );
    expect(result).toEqual({
      items: Array.from({ length: total }, (_, i) => usageRow(i)),
      total,
      complete: true,
    });
    expect(request).toHaveBeenCalledTimes(1);
  });

  it.each([256, 257])("reads every authorized row across pages at %i rows", async (total) => {
    request.mockImplementation((_path, { query }) =>
      Promise.resolve(page(total, query.offset ?? 0, query.limit)),
    );
    const result = await readCorporateCatalogUsage(
      "token",
      organizationId,
      "component",
      stableId,
    );
    expect(result?.items).toHaveLength(total);
    expect(result?.total).toBe(total);
    expect(result?.complete).toBe(true);
    expect(request).toHaveBeenCalledTimes(Math.ceil(total / 256));
  });

  it("stops at the bounded page budget and marks the set incomplete", async () => {
    const total = 256 * 4 + 1;
    request.mockImplementation((_path, { query }) =>
      Promise.resolve(page(total, query.offset ?? 0, query.limit)),
    );
    const result = await readCorporateCatalogUsage(
      "token",
      organizationId,
      "component",
      stableId,
    );
    expect(result?.items).toHaveLength(1024);
    expect(result?.total).toBe(total);
    expect(result?.complete).toBe(false);
    expect(request).toHaveBeenCalledTimes(4);
  });

  it("requests each page at the accumulated offset", async () => {
    const total = 300;
    request.mockImplementation((_path, { query }) =>
      Promise.resolve(page(total, query.offset ?? 0, query.limit)),
    );
    await readCorporateCatalogUsage("token", organizationId, "component", stableId);
    expect(request.mock.calls.map(([, input]) => input.query.offset)).toEqual([0, 256]);
  });

  it.each([401, 403, 404])("returns null when the API refuses with %i", async (status) => {
    request.mockRejectedValue(
      new ApiError({ code: "AI_STP_FORBIDDEN", message: "Denied", status }),
    );
    await expect(
      readCorporateCatalogUsage("token", organizationId, "component", stableId),
    ).resolves.toBeNull();
  });

  it("propagates a non-authorization failure", async () => {
    request.mockRejectedValue(new ApiError({ code: "AI_STP_INTERNAL", message: "Boom", status: 500 }));
    await expect(
      readCorporateCatalogUsage("token", organizationId, "component", stableId),
    ).rejects.toThrow(ApiError);
  });
});
