export const CONTEXT_SURFACES = [
  { key: "projects", href: "/workspace?surface=projects", capability: "project.list" },
  { key: "technology", href: "/catalog?resource=components", capability: "technology.list" },
  { key: "landscape", href: "/services", capability: "landscape.list" },
  { key: "catalog", href: "/catalog", capability: "catalog_object.list" },
] as const;

export type ContextSurfaceKey = (typeof CONTEXT_SURFACES)[number]["key"];

export const CORPORATE_SURFACES = [
  { key: "teams", capability: "team.manage" },
  { key: "assignments", capability: "assignment.assign" },
  { key: "audit", capability: "audit.read" },
  { key: "saml", capability: "saml.manage" },
] as const;

export const PRODUCT_CONTEXT_MODES = ["local", "personal", "corporate"] as const;
export type ProductContextMode = (typeof PRODUCT_CONTEXT_MODES)[number];

/** Closed browser matrix: the server projection still decides availability. */
export const CONTEXT_SURFACE_MATRIX = {
  local: {
    projects: "project.list",
    technology: "technology.list",
    landscape: "landscape.list",
    catalog: "catalog_object.list",
  },
  personal: {
    projects: "project.list",
    technology: "technology.list",
    landscape: "landscape.list",
    catalog: "catalog_object.list",
  },
  corporate: {
    projects: "project.list",
    technology: "technology.list",
    landscape: "landscape.list",
    catalog: "catalog_object.list",
  },
} as const satisfies Record<ProductContextMode, Record<ContextSurfaceKey, string>>;

export function surfaceCapability(mode: ProductContextMode, surface: ContextSurfaceKey): string {
  return CONTEXT_SURFACE_MATRIX[mode][surface];
}
