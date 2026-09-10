import type { ActiveContext, OrganizationSummary } from "@/lib/api/generated/types.gen";

export { ORGANIZATION_COOKIE, PRODUCT_MODE_COOKIE } from "@/lib/context-cookies";

export type ProductContextStatus =
  | "loading"
  | "empty"
  | "ready"
  | "partial"
  | "failed"
  | "unauthenticated"
  | "forbidden"
  | "unavailable"
  | "unsupported"
  | "stale";

export type ProductContextSnapshot = {
  context: ActiveContext;
  organizations: OrganizationSummary[];
  status: ProductContextStatus;
  localAvailable: boolean;
};

export const LOCAL_CONTEXT: ActiveContext = {
  schema_version: 1,
  mode: "local",
  organization_id: null,
  capabilities: {
    schema_version: 1,
    mode: "local",
    context_kind: "local",
    organization_id: null,
    authorization_revision: "local:1",
    generated_at: "1970-01-01T00:00:00.000Z",
    issued_at: "1970-01-01T00:00:00.000Z",
    expires_at: "9999-12-31T23:59:59.999Z",
    capabilities: [
      "catalog_object.list",
      "catalog_object.read",
      "landscape.list",
      "landscape.read",
      "project.list",
      "project.read",
      "technology.list",
      "technology.read",
    ],
    unavailable: {},
  },
};

export function hasCapability(context: ActiveContext, capability: string): boolean {
  return context.capabilities.capabilities.includes(capability);
}

export function contextCacheKey(context: ActiveContext): string {
  return `${context.organization_id ?? context.mode}:${context.capabilities.authorization_revision}`;
}

export function contextStatus(
  snapshot: Pick<ProductContextSnapshot, "context" | "organizations" | "status">,
): ProductContextStatus {
  if (snapshot.status !== "ready") return snapshot.status;
  if (snapshot.context.mode !== "local" && snapshot.organizations.length === 0) return "empty";
  return "ready";
}
