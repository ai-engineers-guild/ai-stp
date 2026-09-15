import type {
  CorporateOverview,
  CorporateOverviewNode,
  CorporateDirectoryReference,
} from "@/lib/api/generated/types.gen";

export function nodeTechnologies(node: CorporateOverviewNode): CorporateDirectoryReference[] {
  return Array.isArray(node.technologies)
    ? (node.technologies as CorporateDirectoryReference[])
    : [];
}

import type { IconName } from "@/theme";

export type OverviewFilters = Record<CorporateOverviewNode["kind"], string[]>;
export const overviewEntityIcons: Record<string, IconName> = {
  project: "component",
  team: "team",
  employee: "user",
  component: "component",
  setup: "setup",
};
export function overviewAssignmentHref(item: CorporateOverviewNode["assignments"][number]) {
  return `/catalog/${item.object_kind === "setup" ? "setups" : "components"}/${encodeURIComponent(item.stable_id)}/versions/${encodeURIComponent(item.version)}`;
}
export type OverviewBranch = {
  node: CorporateOverviewNode;
  children: OverviewBranch[];
  role?: string | undefined;
};

/** OR within a selection, AND along a branch; preserve ancestors of a match. */
export function overviewForest(
  graph: CorporateOverview,
  filters: OverviewFilters,
  query = "",
): OverviewBranch[] {
  const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
  const children = new Map<string, CorporateOverview["edges"]>();
  const parented = new Set<string>();
  for (const edge of graph.edges) {
    children.set(edge.parent_id, [...(children.get(edge.parent_id) ?? []), edge]);
    parented.add(edge.child_id);
  }
  const search = query.trim().toLocaleLowerCase();
  function branch(
    node: CorporateOverviewNode,
    ancestors: CorporateOverviewNode[] = [],
    role?: string,
  ): OverviewBranch | null {
    const path = [...ancestors, node];
    if (filters[node.kind].length && !filters[node.kind].includes(node.id)) return null;
    const descendants = (children.get(node.id) ?? []).flatMap((edge) => {
      const child = nodes.get(edge.child_id);
      if (!child || path.some((item) => item.id === child.id)) return [];
      const result = branch(child, path, edge.role);
      return result ? [result] : [];
    });
    const requiredBelow =
      node.kind === "project"
        ? filters.team.length > 0 || filters.employee.length > 0
        : node.kind === "team" && filters.employee.length > 0;
    if (requiredBelow && !descendants.length) return null;
    if (
      search &&
      !path.some((item) =>
        `${item.name} ${typeof item.description === "string" ? item.description : ""} ${nodeTechnologies(
          item,
        )
          .map((technology) => technology.name)
          .join(
            " ",
          )} ${item.assignments.map((assignment) => assignment.display_name ?? "").join(" ")}`
          .toLocaleLowerCase()
          .includes(search),
      ) &&
      !descendants.length
    )
      return null;
    return { node, children: descendants, role };
  }
  return graph.nodes
    .filter((node) => !parented.has(node.id))
    .flatMap((node) => {
      if (node.kind !== "project" && filters.project.length) return [];
      if (node.kind === "employee" && filters.team.length) return [];
      const result = branch(node);
      return result ? [result] : [];
    });
}

export function corporateNodeHref(node: CorporateOverviewNode): string {
  const resource = node.kind === "employee" ? "members" : `${node.kind}s`;
  return `/corporate/${resource}/${encodeURIComponent(node.id)}`;
}

export function overviewUsage(graph: CorporateOverview) {
  const objects = new Map<
    string,
    {
      assignment: CorporateOverviewNode["assignments"][number];
      versions: CorporateOverviewNode["assignments"];
      nodes: CorporateOverviewNode[];
    }
  >();
  for (const node of graph.nodes) {
    if (!node.assignments_readable) continue;
    for (const assignment of node.assignments) {
      const key = `${assignment.object_kind}:${assignment.stable_id}`;
      const row = objects.get(key) ?? { assignment, versions: [], nodes: [] };
      if (!row.versions.some((item) => item.version === assignment.version))
        row.versions.push(assignment);
      if (!row.nodes.some((item) => item.id === node.id)) row.nodes.push(node);
      objects.set(key, row);
    }
  }
  return [...objects.values()];
}
