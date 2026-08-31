import type { FeatureKey } from "@/lib/features/definitions";
import { COMPONENT_TYPE_FACETS } from "@/lib/tag-vocabulary";

/** Closed component-type set for machine object documents (REQ-3621). */
export const COMPONENT_TYPES = COMPONENT_TYPE_FACETS;

export type ComponentTypeId = (typeof COMPONENT_TYPES)[number];

export type PageAccess = "public" | "session";
export type PresenterKind = "domain" | "generic";

export type PageInventoryEntry = {
  pattern: string;
  access: PageAccess;
  feature?: FeatureKey;
  envGate?: "external_catalog";
  presenter: PresenterKind;
};

/**
 * One entry per human `page.tsx`. The machine registry must cover every
 * pattern; a page without a pair is a defect (REQ-3622).
 */
export const PAGE_INVENTORY: readonly PageInventoryEntry[] = [
  { pattern: "", access: "public", presenter: "domain" },
  { pattern: "catalog", access: "public", presenter: "domain" },
  { pattern: "catalog/components/:stableId", access: "public", presenter: "domain" },
  {
    pattern: "catalog/components/:stableId/versions/:version",
    access: "public",
    presenter: "domain",
  },
  { pattern: "catalog/setups/:stableId", access: "public", presenter: "domain" },
  {
    pattern: "catalog/setups/:stableId/versions/:version",
    access: "public",
    presenter: "domain",
  },
  { pattern: "publishers/:account", access: "public", presenter: "domain" },
  { pattern: "legal/:slug", access: "public", feature: "saas_public_pages", presenter: "domain" },
  { pattern: "docs/*", access: "public", presenter: "domain" },
  { pattern: "content", access: "public", feature: "content_hub", presenter: "domain" },
  {
    pattern: "content/:type/:slug",
    access: "public",
    feature: "content_hub",
    presenter: "domain",
  },
  { pattern: "services", access: "public", presenter: "domain" },
  {
    pattern: "services/:domain",
    access: "public",
    envGate: "external_catalog",
    presenter: "domain",
  },
  {
    pattern: "countries/:code",
    access: "public",
    envGate: "external_catalog",
    presenter: "domain",
  },
  { pattern: "contact", access: "public", feature: "saas_public_pages", presenter: "generic" },
  { pattern: "login", access: "public", presenter: "generic" },
  { pattern: "device-login", access: "public", presenter: "generic" },
  { pattern: "onboarding", access: "session", presenter: "generic" },
  { pattern: "account", access: "session", presenter: "domain" },
  { pattern: "account/privacy", access: "session", presenter: "domain" },
  { pattern: "account/profile", access: "session", presenter: "domain" },
  { pattern: "account/profile/preview", access: "session", presenter: "domain" },
  { pattern: "devices", access: "session", presenter: "domain" },
  { pattern: "objects", access: "session", presenter: "domain" },
  { pattern: "likes", access: "session", presenter: "domain" },
  { pattern: "objects/component/:stableId/edit", access: "session", presenter: "domain" },
  {
    pattern: "objects/:kind/:stableId/versions/:version",
    access: "session",
    presenter: "domain",
  },
  { pattern: "objects/:kind/:stableId", access: "session", presenter: "domain" },
  { pattern: "access", access: "session", presenter: "domain" },
  { pattern: "reports", access: "session", presenter: "domain" },
  { pattern: "publications/:planId", access: "session", presenter: "domain" },
  { pattern: "invitations/:invitationId", access: "session", presenter: "domain" },
  { pattern: "staff/reports", access: "session", presenter: "domain" },
  { pattern: "staff/reports/:caseId", access: "session", presenter: "domain" },
];

export const PAGE_INVENTORY_PATTERNS = PAGE_INVENTORY.map((entry) => entry.pattern);

/** Convert a human `page.tsx` path under `(site)` into an inventory pattern. */
export function pageFileToPattern(relativeFromSite: string): string {
  const normalized = relativeFromSite.replace(/\\/g, "/");
  const withoutFile = normalized === "page.tsx" ? "" : normalized.replace(/\/page\.tsx$/, "");
  const parts = withoutFile.split("/").filter((part) => part.length > 0 && !part.startsWith("("));
  if (parts.length === 0) return "";
  return parts
    .map((part) => {
      if (part.startsWith("[[...") && part.endsWith("]]")) return "*";
      if (part.startsWith("[") && part.endsWith("]")) return `:${part.slice(1, -1)}`;
      return part;
    })
    .join("/");
}

export function isComponentType(value: string): value is ComponentTypeId {
  return (COMPONENT_TYPES as readonly string[]).includes(value);
}

/** Same runtime gate the human country/service pages use. */
export function isExternalCatalogEnabled(): boolean {
  return process.env.NEXT_PUBLIC_EXTERNAL_CATALOG_ENABLED !== "false";
}
