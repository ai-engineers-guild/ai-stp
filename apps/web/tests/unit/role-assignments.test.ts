import { describe, expect, it } from "vitest";

import { collectRoleAssignmentRows } from "@/lib/role-assignments";
import type { CorporateBinding, CorporateMember } from "@/lib/api/generated/types.gen";

const member = (accountId: string, role: string, name = accountId): CorporateMember =>
  ({
    account_id: accountId,
    display_name: name,
    role,
    state: "active",
    schema_version: 1,
  }) as unknown as CorporateMember;

const binding = (overrides: Partial<CorporateBinding>): CorporateBinding => ({
  account_id: "account_a",
  binding_id: `binding_${Math.random()}`,
  coverage: "self",
  origin: "direct",
  principal_type: "user",
  revision: 1,
  role: "lead",
  schema_version: 1,
  scope_id: "organization_1",
  scope_kind: "organization",
  service_principal_id: null,
  state: "active",
  ...overrides,
});

const scopeName = (kind: string, id: string) => `${kind}:${id}`;

describe("collectRoleAssignmentRows", () => {
  it("merges membership and direct binding on the same scope into one row", () => {
    const rows = collectRoleAssignmentRows({
      bindings: [
        binding({ origin: "membership", binding_id: "b1" }),
        binding({ origin: "direct", binding_id: "b2" }),
      ],
      members: [member("account_a", "lead", "Alice")],
      roleName: "lead",
      organizationId: "organization_1",
      scopeName,
    });
    expect(rows).toHaveLength(1);
    expect(rows.at(0)?.origins).toEqual(["membership", "direct"]);
    expect(rows.at(0)?.name).toBe("Alice");
  });

  it("keeps distinct scopes as separate rows and ignores other roles", () => {
    const rows = collectRoleAssignmentRows({
      bindings: [
        binding({ binding_id: "b1", scope_kind: "team", scope_id: "team_1", origin: "assignment" }),
        binding({ binding_id: "b2", scope_kind: "team", scope_id: "team_2", origin: "assignment" }),
        binding({ binding_id: "b3", role: "staff", scope_kind: "team", scope_id: "team_1" }),
        binding({ binding_id: "b4", state: "revoked" }),
      ],
      members: [],
      roleName: "lead",
      organizationId: "organization_1",
      scopeName,
    });
    expect(rows.map((row) => row.scopeLabel)).toEqual(["team:team_1", "team:team_2"]);
  });

  it("keys service principals separately from users", () => {
    const rows = collectRoleAssignmentRows({
      bindings: [
        binding({
          binding_id: "b1",
          account_id: null,
          principal_type: "service_principal",
          service_principal_id: "sp_1",
        }),
      ],
      members: [],
      roleName: "lead",
      organizationId: "organization_1",
      scopeName,
    });
    expect(rows).toHaveLength(1);
    expect(rows.at(0)?.accountId).toBeNull();
    expect(rows.at(0)?.origins).toEqual(["direct"]);
  });
});
