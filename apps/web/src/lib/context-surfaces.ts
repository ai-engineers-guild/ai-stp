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
