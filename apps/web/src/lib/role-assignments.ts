import type { CorporateBinding, CorporateMember } from "@/lib/api/generated/types.gen";

export const BINDING_ORIGIN_ORDER = [
  "membership",
  "assignment",
  "direct",
  "service_principal",
] as const;

export type BindingOrigin = (typeof BINDING_ORIGIN_ORDER)[number];

export type RoleAssignmentRow = {
  key: string;
  accountId: string | null;
  name: string;
  scopeKind: string;
  scopeLabel: string;
  origins: BindingOrigin[];
};

/**
 * One row per (principal, scope) for a role: the organization membership,
 * scoped bindings, and direct grants share the key so merged rows carry every
 * origin instead of rendering one row per source.
 */
export function collectRoleAssignmentRows({
  bindings,
  members,
  roleName,
  organizationId,
  scopeName,
}: {
  bindings: readonly CorporateBinding[];
  members: readonly CorporateMember[];
  roleName: string;
  organizationId: string;
  scopeName: (kind: string, id: string) => string;
}): RoleAssignmentRow[] {
  const rows = new Map<
    string,
    { base: Omit<RoleAssignmentRow, "key" | "origins">; origins: Set<BindingOrigin> }
  >();
  const add = (
    key: string,
    origin: BindingOrigin,
    base: Omit<RoleAssignmentRow, "key" | "origins">,
  ) => {
    const existing = rows.get(key);
    if (existing) existing.origins.add(origin);
    else rows.set(key, { base, origins: new Set([origin]) });
  };
  for (const member of members) {
    if (member.role !== roleName || member.state !== "active") continue;
    add(`user:${member.account_id}:organization:${organizationId}`, "membership", {
      accountId: member.account_id,
      name: member.display_name ?? member.account_id,
      scopeKind: "organization",
      scopeLabel: scopeName("organization", organizationId),
    });
  }
  for (const binding of bindings) {
    if (binding.role !== roleName || binding.state !== "active") continue;
    const principal = binding.account_id ?? binding.service_principal_id;
    if (!principal) continue;
    add(
      `${binding.principal_type}:${principal}:${binding.scope_kind}:${binding.scope_id}`,
      binding.origin,
      {
        accountId: binding.account_id,
        name:
          members.find((member) => member.account_id === binding.account_id)?.display_name ??
          principal,
        scopeKind: binding.scope_kind,
        scopeLabel: scopeName(binding.scope_kind, binding.scope_id),
      },
    );
  }
  return [...rows.entries()].map(([key, { base, origins }]) => ({
    key,
    ...base,
    origins: BINDING_ORIGIN_ORDER.filter((origin) => origins.has(origin)),
  }));
}
