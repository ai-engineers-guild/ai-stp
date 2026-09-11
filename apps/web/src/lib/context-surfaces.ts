export const CONTEXT_SURFACES = [
  { key: "projects", href: "/workspace?surface=projects", capability: "project.list" },
  { key: "technology", href: "/catalog?resource=components", capability: "technology.list" },
  { key: "landscape", href: "/services", capability: "landscape.list" },
  { key: "catalog", href: "/catalog", capability: "catalog_object.list" },
] as const;

export type ContextSurfaceKey = (typeof CONTEXT_SURFACES)[number]["key"];

export const CORPORATE_SURFACES = [
  { key: "teams", href: "/workspace?surface=teams", capability: "team.manage" },
  {
    key: "assignments",
    href: "/workspace?surface=assignments",
    capability: "assignment.assign",
  },
  { key: "audit", href: "/workspace?surface=audit", capability: "audit.read" },
  { key: "saml", href: "/workspace?surface=saml", capability: "saml.manage" },
] as const;

export type CorporateSurfaceKey = (typeof CORPORATE_SURFACES)[number]["key"];
