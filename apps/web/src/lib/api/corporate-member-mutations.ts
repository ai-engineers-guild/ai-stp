import { corporateMutation, corporateTeamAssignments } from "@/lib/api/corporate-mutation";
import type { CorporateContext, CorporateMember } from "@/lib/api/generated/types.gen";

export const baseBody = (revision: number, authorizationRevision: number | string) => ({
  schema_version: 1,
  expected_revision: revision,
  authorization_revision: authorizationRevision,
});

export const fieldValue = (data: FormData, name: string) => {
  const value = data.get(name);
  return typeof value === "string" ? value.trim() : "";
};

export function readRevision(data: unknown): number | null {
  const revision = (data as { revision?: unknown } | null)?.revision;
  return typeof revision === "number" ? revision : null;
}

/** Diffs the member's team memberships and lead flags, then applies the delta. */
export function saveTeams(
  member: CorporateMember,
  context: CorporateContext,
  csrfToken: string,
  teamIds: string[],
  leadIds: Set<string>,
): Promise<string | null> {
  const selected = new Set(teamIds);
  const leads = new Set([...leadIds].filter((id) => selected.has(id)));
  const current = new Set(
    context.teams
      .filter((team) => team.members.some((entry) => entry.account_id === member.account_id))
      .map((team) => team.team_id),
  );
  const wasLead = new Set(
    context.teams
      .filter((team) => team.lead_account_ids.includes(member.account_id))
      .map((team) => team.team_id),
  );
  const assignments = [
    ...[...selected]
      .filter((id) => !current.has(id) || leads.has(id) !== wasLead.has(id))
      .map((teamId) => ({
        accountId: member.account_id,
        teamId,
        role: leads.has(teamId) ? ("lead" as const) : ("staff" as const),
        operation: "assign" as const,
        idempotencyKey: crypto.randomUUID(),
      })),
    ...[...current]
      .filter((id) => !selected.has(id))
      .map((teamId) => ({
        accountId: member.account_id,
        teamId,
        role: "staff" as const,
        operation: "remove" as const,
        idempotencyKey: crypto.randomUUID(),
      })),
  ];
  if (!assignments.length) return Promise.resolve(null);
  return corporateTeamAssignments({
    csrfToken,
    organizationId: context.organization.organization_id,
    assignments,
  }).then((result) =>
    result.completed.length === assignments.length
      ? null
      : (result.message ?? "Some team assignments failed"),
  );
}

/** Applies the non-empty bulk fields to one member; returns 1 on any failed leg. */
export async function applyBulkChange(
  member: CorporateMember,
  {
    role,
    jobTitle,
    teamId,
    context,
    csrfToken,
    authorizationRevision,
    canMemberUpdate,
  }: {
    role: string;
    jobTitle: string;
    teamId: string;
    context: CorporateContext;
    csrfToken: string;
    authorizationRevision: number | string;
    canMemberUpdate: boolean;
  },
): Promise<number> {
  const organizationId = context.organization.organization_id;
  let failed = 0;
  const wantsMembershipChange =
    (role && role !== member.role) ||
    (jobTitle === "__none__" && member.job_title_id) ||
    (jobTitle && jobTitle !== "__none__" && jobTitle !== member.job_title_id);
  if (canMemberUpdate && wantsMembershipChange) {
    const result = await corporateMutation({
      csrfToken,
      organizationId,
      path: `/v1/corporate/organizations/${organizationId}/members/${member.account_id}`,
      method: "PATCH",
      body: {
        ...baseBody(member.revision, authorizationRevision),
        role: role || member.role,
        state: member.state,
        job_title_id: jobTitle === "__none__" ? null : jobTitle || member.job_title_id,
        idempotency_key: crypto.randomUUID(),
      },
    });
    if (!result.ok) failed += 1;
  }
  if (teamId) {
    const already = context.teams.some(
      (team) =>
        team.team_id === teamId &&
        team.members.some((entry) => entry.account_id === member.account_id),
    );
    if (!already) {
      const result = await corporateTeamAssignments({
        csrfToken,
        organizationId,
        assignments: [
          {
            accountId: member.account_id,
            teamId,
            role: "staff",
            operation: "assign",
            idempotencyKey: crypto.randomUUID(),
          },
        ],
      });
      if (!result.completed.length) failed += 1;
    }
  }
  return failed;
}
