import type { ComponentType, CorporateDirectoryReference } from "@/lib/api/generated/types.gen";

export type DirectoryRef = Pick<CorporateDirectoryReference, "id" | "name"> & {
  /** Catalog relations use the same card surface even though directory facets omit these kinds. */
  kind?: CorporateDirectoryReference["kind"] | "component" | "setup";
};

export type DirectoryResource = "teams" | "projects" | "technologies" | "members" | "components";
export type DirectoryFacet =
  "leads" | "teams" | "technologies" | "projects" | "categories" | "job_titles";
export type CorporateCatalogFacet =
  | "team_ids"
  | "project_ids"
  | "technology_ids"
  | "category_ids"
  | "owner_ids"
  | "maintainer_ids"
  | "assignment"
  | "corporate_verified";
export type CorporateCatalogFacetConfig = {
  key: CorporateCatalogFacet;
  label: string;
  options: readonly { value: string; label: string }[];
  multiple?: boolean;
};

export type DirectoryItem = {
  id: string;
  name: string;
  description?: string;
  role?: string | null;
  leads?: readonly DirectoryRef[];
  teams?: readonly DirectoryRef[];
  related_teams?: readonly DirectoryRef[];
  projects?: readonly DirectoryRef[];
  technologies?: readonly DirectoryRef[];
  owner_team?: DirectoryRef | null;
  owner?: DirectoryRef | null;
  job_title?: DirectoryRef | null;
  categories?: readonly DirectoryRef[];
  available_actions?: readonly string[];
  is_lead?: boolean;
  component_type?: ComponentType;
  author_name?: string | null;
  owner_name?: string | null;
  tags?: readonly string[];
  version?: string | null;
};

export const directoryFacets: Record<DirectoryResource, DirectoryFacet[]> = {
  teams: ["leads", "technologies", "teams"],
  projects: ["teams", "technologies"],
  technologies: ["projects", "teams", "categories"],
  members: ["projects", "teams", "technologies", "job_titles"],
  components: [],
};

export const directoryFacetParams: Record<DirectoryFacet, string> = {
  leads: "lead_ids",
  teams: "team_ids",
  technologies: "technology_ids",
  projects: "project_ids",
  categories: "category_ids",
  job_titles: "job_title_ids",
};

export function directoryReferences(
  item: DirectoryItem,
  facet: DirectoryFacet,
): readonly DirectoryRef[] {
  if (facet === "teams") {
    return [
      ...(item.teams ?? []),
      ...(item.related_teams ?? []),
      ...(item.owner_team ? [item.owner_team] : []),
    ];
  }
  if (facet === "job_titles") return item.job_title ? [item.job_title] : [];
  return item[facet] ?? [];
}

export function directoryHref(resource: DirectoryResource, id: string, returnFilters = "") {
  if (resource === "components") {
    const returnTo = `/corporate/catalog${returnFilters ? `?${returnFilters}` : ""}`;
    return `/catalog/components/${encodeURIComponent(id)}?return_to=${encodeURIComponent(returnTo)}`;
  }
  const routeResource = resource === "members" ? "employees" : resource;
  return `/corporate/${routeResource}/${encodeURIComponent(id)}${returnFilters ? `?${returnFilters}` : ""}`;
}

export function isComponentType(value: string | undefined): value is ComponentType {
  return [
    "instruction",
    "skill",
    "mcp",
    "hook",
    "command",
    "agent",
    "plugin",
    "setting",
    "cli",
  ].includes(value ?? "");
}
