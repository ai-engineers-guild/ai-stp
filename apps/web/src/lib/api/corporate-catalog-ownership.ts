import { privateApiRequest } from "@/lib/api/http";
import { ApiError } from "@/lib/api/errors";
import { readCorporateContext, readCorporateDirectoryPages } from "./corporate";
import { z } from "zod";

import { tryAsAccountId, tryAsComponentId, tryAsSetupId } from "@/lib/brands";
import type {
  CorporateCatalogOwnership,
  CorporateCatalogUsageList,
  CorporateDirectoryItem,
  CorporateContext,
} from "./generated/types.gen";
import type { ComponentId, SetupId, VersionId } from "@/lib/brands";

export type CorporateCatalogObjectKind = "component" | "setup";

export type CorporateCatalogOwnerMember = Pick<CorporateDirectoryItem, "id" | "name" | "state">;

export type CorporateCatalogOwnershipData = {
  ownership: CorporateCatalogOwnership;
  authorizationRevision: number;
  members: CorporateCatalogOwnerMember[] | null;
};

const corporateCatalogOwnershipSchema = z.object({
  can_edit: z.boolean(),
  capabilities: z.array(z.string()).default([]),
  object_kind: z.enum(["setup", "component"]),
  organization_id: z.string(),
  owner_id: z.string().nullable(),
  owner_kind: z.enum(["organization", "team", "project", "technology", "employee"]),
  owner_account_id: z
    .string()
    .refine((value) => tryAsAccountId(value) !== null, "invalid owner account id")
    .nullable(),
  owner_display_name: z.string().nullable(),
  revision: z.number().int().nonnegative(),
  schema_version: z.literal(1),
  stable_id: z.string(),
});

export async function readCorporateCatalogOwnershipSummary(
  sessionToken: string,
  organizationId: string,
  objectKind: CorporateCatalogObjectKind,
  stableId: ComponentId | SetupId,
  version: VersionId,
): Promise<CorporateCatalogOwnership | null> {
  const validStableId =
    objectKind === "component" ? tryAsComponentId(stableId) : tryAsSetupId(stableId);
  if (!validStableId) throw new Error("invalid catalog ownership target");
  try {
    const ownership = corporateCatalogOwnershipSchema.parse(
      await privateApiRequest<unknown>(
        `/v1/corporate/organizations/${organizationId}/catalog-ownership`,
        { sessionToken, query: { object_kind: objectKind, stable_id: stableId, version } },
      ),
    );
    if (
      ownership.organization_id !== organizationId ||
      ownership.object_kind !== objectKind ||
      ownership.stable_id !== stableId
    )
      throw new Error("catalog ownership response does not match the requested target");
    return ownership;
  } catch (error) {
    if (error instanceof ApiError && [401, 403, 404].includes(error.status)) return null;
    throw error;
  }
}

export async function readCorporateCatalogOwnership(
  sessionToken: string,
  objectKind: CorporateCatalogObjectKind,
  stableId: ComponentId | SetupId,
  version: VersionId,
  corporateContext?: CorporateContext | null,
): Promise<CorporateCatalogOwnershipData | null> {
  const validStableId =
    objectKind === "component" ? tryAsComponentId(stableId) : tryAsSetupId(stableId);
  if (!validStableId) throw new Error("invalid catalog ownership target");
  try {
    const context =
      corporateContext === undefined ? await readCorporateContext(sessionToken) : corporateContext;
    if (!context) return null;
    const organizationId = context.organization.organization_id;
    const ownership = await readCorporateCatalogOwnershipSummary(
      sessionToken,
      organizationId,
      objectKind,
      stableId,
      version,
    );
    if (!ownership) return null;
    const members =
      ownership.can_edit && context.capabilities.includes("member.list")
        ? (
            await readCorporateDirectoryPages(sessionToken, organizationId, {
              resource: "members",
              include_archived: true,
            })
          ).items
            .filter((item) => item.state === "active")
            .map(({ id, name, state }) => ({ id, name, state }))
        : null;
    return {
      ownership,
      authorizationRevision: context.organization.authorization_revision,
      members,
    };
  } catch (error) {
    if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
      return null;
    }
    throw error;
  }
}

const CATALOG_USAGE_PAGE_LIMIT = 256;
const CATALOG_USAGE_MAX_PAGES = 4;

export type CorporateCatalogUsagePage = {
  items: CorporateCatalogUsageList["items"];
  total: number;
  /** False when the bounded read stopped before every authorized row arrived. */
  complete: boolean;
};

export async function readCorporateCatalogUsage(
  sessionToken: string,
  organizationId: string,
  objectKind: CorporateCatalogObjectKind,
  stableId: ComponentId | SetupId,
): Promise<CorporateCatalogUsagePage | null> {
  const validStableId =
    objectKind === "component" ? tryAsComponentId(stableId) : tryAsSetupId(stableId);
  if (!validStableId) throw new Error("invalid catalog usage target");
  const items: CorporateCatalogUsageList["items"] = [];
  let total = 0;
  try {
    for (let page = 0; page < CATALOG_USAGE_MAX_PAGES; page++) {
      const slice = await privateApiRequest<CorporateCatalogUsageList>(
        `/v1/corporate/organizations/${organizationId}/catalog-usage`,
        {
          sessionToken,
          query: {
            object_kind: objectKind,
            stable_id: stableId,
            offset: items.length,
            limit: CATALOG_USAGE_PAGE_LIMIT,
          },
        },
      );
      total = slice.total;
      items.push(...slice.items);
      if (!slice.items.length || items.length >= slice.total) break;
    }
  } catch (error) {
    if (error instanceof ApiError && [401, 403, 404].includes(error.status)) return null;
    throw error;
  }
  return { items, total, complete: items.length >= total };
}
