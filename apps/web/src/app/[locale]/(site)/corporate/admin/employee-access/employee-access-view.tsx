import { getTranslations } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateEmployeeAccessDrawer } from "@/components/organisms/corporate-employee-access-drawer";
import { CorporateMemberAccessPanel } from "@/components/organisms/corporate-member-access-panel";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import { readCorporateAudit } from "@/lib/api/corporate-audit";
import {
  readCorporateCatalogScopeOptions,
  readCorporateCategoryScopeOptions,
  readCorporateScopeTechnologies,
  readCorporateMemberAccess,
} from "@/lib/api/corporate";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import type {
  CorporateDirectoryItem,
  CorporatePermissionMatrix,
} from "@/lib/api/generated/types.gen";

const SCOPE_KINDS = [
  "organization",
  "team",
  "project",
  "technology",
  "catalog_object",
  "member",
] as const;

type MemberAccessResult = Awaited<ReturnType<typeof readCorporateMemberAccess>>;

/**
 * Employee access content for the directory drawer (`?employee=`). The old
 * standalone `[accountId]` route redirects here, so this view has exactly one
 * layout: the shared People & Access drawer. Callers own session gating.
 */
export async function EmployeeAccessView({
  accountId,
  filters,
}: {
  accountId: string;
  filters: Record<string, string | string[] | undefined>;
}) {
  const { kind: requestedScopeKind, id: requestedScopeId } = requestedScope(filters);
  const t = await getTranslations("corporate");
  const tc = await getTranslations("common");
  const technology = await getTranslations("technology");

  let result: MemberAccessResult;
  try {
    result = await loadMemberAccess(accountId, requestedScopeKind, requestedScopeId);
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return (
        <StatePanel
          kind="error"
          title={t("employeeAccessTitle")}
          description={tc("apiUnavailable")}
        />
      );
    }
    throw error;
  }
  if (!result)
    return (
      <StatePanel
        kind="error"
        title={t("employeeAccessTitle")}
        description={technology("forbidden")}
      />
    );

  const { member, access, context, organization } = result;
  const capabilities = context.capabilities;
  const csrfToken = (await readCsrfToken()) ?? "";
  const session = (await sessionCookieValue()) ?? "";
  const permissionMatrix = capabilities.includes("role.read")
    ? await apiRequest<CorporatePermissionMatrix>(
        `/v1/corporate/organizations/${organization.organization_id}/permissions/matrix`,
        { sessionToken: session },
      )
    : null;
  const technologies = await readCorporateScopeTechnologies(
    session,
    organization.organization_id,
    capabilities,
  );
  const definitions = permissionMatrix?.definitions ?? [];
  const { scopeOptions, currentScope, effective } = deriveAccessView(
    result,
    requestedScopeKind,
    requestedScopeId,
    t,
    technologies,
  );
  scopeOptions.push(
    ...(await readCorporateCatalogScopeOptions(
      session,
      organization.organization_id,
      capabilities,
    )),
    ...(await readCorporateCategoryScopeOptions(
      session,
      organization.organization_id,
      capabilities,
    )),
  );

  const a = await getTranslations("accessUi");
  const accessPanel = (
    <CorporateMemberAccessPanel
      csrfToken={csrfToken}
      organizationId={organization.organization_id}
      authorizationRevision={organization.authorization_revision}
      membershipRole={member.role}
      scopeOptions={scopeOptions}
      teams={context.teams}
      projects={context.projects}
      bindings={access?.bindings ?? []}
      grants={access?.grants ?? []}
      capabilities={capabilities}
      definitions={definitions}
      labels={{
        ...memberAccessLabels(t),
        bindings: a("rolesAndAssignments"),
      }}
    />
  );
  const activity = await readCorporateAudit(session, { actor_account_id: accountId });
  return (
    <CorporateEmployeeAccessDrawer
      activity={activity?.audit.items ?? []}
      member={member}
      teams={context.teams}
      effective={effective}
      definitions={definitions}
      scopeOptions={scopeOptions}
      currentScope={currentScope}
      canAudit={capabilities.includes("audit.list")}
    >
      {accessPanel}
    </CorporateEmployeeAccessDrawer>
  );
}

function requestedScope(filters: Record<string, string | string[] | undefined>) {
  const parts = typeof filters.scope === "string" ? filters.scope.split(":", 2) : [];
  const kind =
    parts.length === 2 && (SCOPE_KINDS as readonly string[]).includes(parts[0] ?? "")
      ? (parts[0] ?? "organization")
      : "organization";
  return { kind, id: parts.length === 2 ? parts[1] : undefined };
}

function memberAccessLabels(t: (key: string) => string) {
  return {
    bindings: t("roleBindings"),
    role: t("role"),
    scope: t("scope"),
    organization: t("organization"),
    revoke: t("revoke"),
    revoking: t("revoking"),
    coverageSelf: t("coverageSelf"),
    coverageDescendants: t("coverageDescendants"),
    originMembership: t("originMembership"),
    originAssignment: t("originAssignment"),
    originDirect: t("originDirect"),
    originServicePrincipal: t("originServicePrincipal"),
    noBindings: t("noBindings"),
    directGrants: t("directGrants"),
    directGrantsBody: t("directGrantsBody"),
    issuer: t("issuer"),
    noGrants: t("noGrants"),
    saved: t("saved"),
    confirmRevoke: t("confirmDelete"),
  };
}

async function loadMemberAccess(
  accountId: string,
  scopeKind: string,
  scopeId: string | undefined,
): Promise<MemberAccessResult> {
  const session = (await sessionCookieValue()) ?? "";
  return readCorporateMemberAccess(session, accountId, {
    scope_kind: scopeKind,
    ...(scopeId ? { scope_id: scopeId } : {}),
  });
}

function deriveAccessView(
  result: NonNullable<MemberAccessResult>,
  requestedScopeKind: string,
  requestedScopeId: string | undefined,
  t: (key: string) => string,
  technologies: readonly CorporateDirectoryItem[],
) {
  const { access, context, organization } = result;
  const scopeKind = access?.scope_kind ?? requestedScopeKind;
  const scopeId = access?.scope_id ?? requestedScopeId ?? organization.organization_id;
  return {
    effective: access?.effective ?? [],
    currentScope: `${scopeKind}:${scopeId}`,
    scopeOptions: [
      { value: `organization:${organization.organization_id}`, label: t("allScopes") },
      ...context.teams.map((team) => ({
        value: `team:${team.team_id}`,
        label: `${t("team")}: ${team.name}`,
      })),
      ...context.projects.map((project) => ({
        value: `project:${project.project_id}`,
        label: `${t("project")}: ${project.name}`,
      })),
      ...technologies.map((item) => ({
        value: `technology:${item.id}`,
        label: item.name,
      })),
    ],
  };
}
