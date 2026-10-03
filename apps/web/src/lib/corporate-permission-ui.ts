import type {
  CorporatePermissionDefinition,
  CorporateRoleView,
} from "@/lib/api/generated/types.gen";
import type { IconName } from "@/theme";

export const ACCESS_GROUPS = [
  "discovery",
  "content",
  "relations",
  "presentation",
  "lifecycle",
] as const;
export const ROLE_COLUMNS = ["list", "read", "create", "update", "delete"] as const;

/** Existing action names are usable even when their scope catalog is not readable. */
export function permissionDefinitions(names: readonly string[]): CorporatePermissionDefinition[] {
  return [...new Set(names)]
    .filter((name) => name.includes("."))
    .map((name) => {
      const dot = name.indexOf(".");
      return {
        name,
        resource: name.slice(0, dot),
        action: name.slice(dot + 1),
        group: name.slice(0, dot),
        scopes: [],
        create_parent: null,
        implementation: "enforced",
      };
    });
}

const entities: Record<string, { icon: IconName; area: string }> = {
  member: { icon: "user", area: "organization" },
  invitation: { icon: "mail", area: "organization" },
  team: { icon: "team", area: "organization" },
  project: { icon: "component", area: "organization" },
  technology: { icon: "technology", area: "product" },
  category: { icon: "filter", area: "referenceData" },
  job_title: { icon: "flag", area: "referenceData" },
  catalog_object: { icon: "objects", area: "product" },
  role: { icon: "access", area: "administration" },
  binding: { icon: "access", area: "administration" },
  organization: { icon: "setup", area: "administration" },
  audit: { icon: "list", area: "administration" },
  service_principal: { icon: "lock", area: "security" },
  telemetry: { icon: "controls", area: "insights" },
  telemetry_usage: { icon: "controls", area: "insights" },
  landscape: { icon: "technology", area: "product" },
};

export function permissionEntity(resource: string) {
  if (["project_team", "project_technology"].includes(resource)) return "project";
  if (["technology_team", "technology_decision"].includes(resource)) return "technology";
  return resource;
}

export function entityMeta(resource: string) {
  return entities[resource] ?? { icon: "objects" as const, area: "administration" };
}

export function entityDefinitions(definitions: readonly CorporatePermissionDefinition[]) {
  const grouped = new Map<string, CorporatePermissionDefinition[]>();
  for (const definition of definitions) {
    const entity =
      definition.name === "member.invite" ? "invitation" : permissionEntity(definition.resource);
    grouped.set(entity, [...(grouped.get(entity) ?? []), definition]);
  }
  return [...grouped.entries()].sort(([a], [b]) => {
    const order = Object.keys(entities);
    return order.indexOf(a) - order.indexOf(b);
  });
}

export function permissionGroup(definition: CorporatePermissionDefinition) {
  if (permissionEntity(definition.resource) !== definition.resource) return "relations";
  if (["list", "read", "explain", "events", "audit"].includes(definition.action))
    return "discovery";
  if (["create", "update", "edit", "invite", "write"].includes(definition.action)) return "content";
  if (
    ["link", "unlink", "assign", "manage", "maintainer", "ownership_transfer"].includes(
      definition.action,
    )
  )
    return "relations";
  if (definition.action === "presentation") return "presentation";
  return "lifecycle";
}

export function permissionColumn(definition: CorporatePermissionDefinition) {
  if (permissionEntity(definition.resource) !== definition.resource) return "other";
  if (definition.action === "edit") return "update";
  return (ROLE_COLUMNS as readonly string[]).includes(definition.action)
    ? definition.action
    : "other";
}

export function rolePermissions(role: CorporateRoleView) {
  return new Set<string>(role.permissions);
}

const actionLabels = [
  "list",
  "read",
  "create",
  "update",
  "edit",
  "delete",
  "invite",
  "manage",
  "link",
  "unlink",
  "export",
  "write",
  "ingest",
  "events",
  "assign",
  "maintainer",
  "ownership_transfer",
  "publish",
  "verify",
  "lifecycle",
  "audit",
  "explain",
  "approve",
  "merge",
  "responsibility",
  "scan_publish",
  "scan",
  "project_team_create",
  "project_team_read",
  "project_team_list",
  "project_team_update",
  "project_team_delete",
  "project_technology_create",
  "project_technology_read",
  "project_technology_list",
  "project_technology_update",
  "project_technology_delete",
  "technology_team_create",
  "technology_team_read",
  "technology_team_list",
  "technology_team_update",
  "technology_team_delete",
  "technology_decision_create",
  "technology_decision_read",
  "technology_decision_list",
  "technology_decision_update",
  "technology_decision_delete",
];

export function permissionLabel(
  definition: CorporatePermissionDefinition,
  t: (key: string) => string,
) {
  const relation = permissionEntity(definition.resource) !== definition.resource;
  const label = relation
    ? `${definition.resource}_${definition.action}`
    : definition.action.replaceAll(".", "_");
  return actionLabels.includes(label) ? t(`actions.${label}`) : definition.name;
}

export function roleTitle(name: string, t: (key: string) => string) {
  return ["superadmin", "lead", "staff"].includes(name) ? t(`roleNames.${name}`) : name;
}
