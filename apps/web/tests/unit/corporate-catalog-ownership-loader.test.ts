import { beforeEach, describe, expect, it, vi } from "vitest";

const { request, context, directory } = vi.hoisted(() => ({
  request: vi.fn(),
  context: vi.fn(),
  directory: vi.fn(),
}));

vi.mock("@/lib/api/http", () => ({ privateApiRequest: request }));
vi.mock("@/lib/api/corporate", () => ({
  readCorporateContext: context,
  readCorporateDirectoryPages: directory,
}));

import { asComponentId, asVersionId } from "@/lib/brands";
import {
  readCorporateCatalogOwnership,
  readCorporateCatalogOwnershipSummary,
} from "@/lib/api/corporate-catalog-ownership";

const organizationId = "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const stableId = asComponentId("component_01JQZK7B8N4M6P2R9T5V0X3Y7Z");
const version = asVersionId("1.2.3");
const ownerId = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z";

beforeEach(() => {
  vi.clearAllMocks();
  context.mockResolvedValue({
    organization: { organization_id: organizationId, authorization_revision: 9 },
    capabilities: ["member.list"],
  });
  request.mockResolvedValue({
    schema_version: 1,
    can_edit: true,
    object_kind: "component",
    organization_id: organizationId,
    owner_id: ownerId,
    owner_kind: "employee",
    owner_account_id: ownerId,
    owner_display_name: "Active employee",
    revision: 4,
    stable_id: stableId,
  });
  directory.mockResolvedValue({
    items: [
      { id: ownerId, name: "Active employee", state: "active" },
      { id: "account_01JQZK7B8N4M6P2R9T5V0X3Y8A", name: "Suspended", state: "suspended" },
    ],
  });
});

describe("corporate catalog ownership loader", () => {
  it("reads Overview owner metadata without loading context or the entire member directory", async () => {
    const result = await readCorporateCatalogOwnershipSummary(
      "session",
      organizationId,
      "component",
      stableId,
      version,
    );
    expect(result?.owner_display_name).toBe("Active employee");
    expect(context).not.toHaveBeenCalled();
    expect(directory).not.toHaveBeenCalled();
    expect(request).toHaveBeenCalledTimes(1);
  });
  it("reads the tenant-scoped owner and only active member choices", async () => {
    const result = await readCorporateCatalogOwnership("session", "component", stableId, version);

    expect(request).toHaveBeenCalledWith(
      `/v1/corporate/organizations/${organizationId}/catalog-ownership`,
      expect.objectContaining({
        sessionToken: "session",
        query: { object_kind: "component", stable_id: stableId, version },
      }),
    );
    expect(directory).toHaveBeenCalledWith("session", organizationId, {
      resource: "members",
      include_archived: true,
    });
    expect(result?.members).toEqual([{ id: ownerId, name: "Active employee", state: "active" }]);
    expect(result?.authorizationRevision).toBe(9);
  });

  it("does not load member choices when the ownership contract denies editing", async () => {
    request.mockResolvedValueOnce({
      schema_version: 1,
      can_edit: false,
      object_kind: "component",
      organization_id: organizationId,
      owner_id: null,
      owner_kind: "employee",
      owner_account_id: null,
      owner_display_name: null,
      revision: 0,
      stable_id: stableId,
    });

    const result = await readCorporateCatalogOwnership("session", "component", stableId, version);

    expect(result?.ownership.owner_account_id).toBeNull();
    expect(result?.members).toBeNull();
    expect(directory).not.toHaveBeenCalled();
  });

  it("rejects a response for another target instead of exposing it", async () => {
    request.mockResolvedValueOnce({
      schema_version: 1,
      can_edit: false,
      object_kind: "setup",
      organization_id: organizationId,
      owner_id: null,
      owner_kind: "employee",
      owner_account_id: null,
      owner_display_name: null,
      revision: 0,
      stable_id: "setup_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    });

    await expect(
      readCorporateCatalogOwnership("session", "component", stableId, version),
    ).rejects.toThrow("does not match");
  });
});
