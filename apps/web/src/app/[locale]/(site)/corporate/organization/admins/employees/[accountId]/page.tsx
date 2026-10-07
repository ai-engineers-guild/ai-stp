import { Select } from "@/components/atoms/select";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { LocalizedResourceActions } from "@/components/organisms/localized-corporate-resource-actions";
import { CorporateMemberAccessPanel } from "@/components/organisms/corporate-member-access-panel";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import { readCorporateMemberAccess } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";
import type {
  CorporateEffectivePermission,
  CorporateMember,
  CorporateMemberPrivateGrant,
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

export default async function EmployeeAccessPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; accountId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale, accountId } = await params;
  const filters = await searchParams;
  const { kind: requestedScopeKind, id: requestedScopeId } = requestedScope(filters);
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/employees/${accountId}`);
  const t = await getTranslations("corporate");
  const tc = await getTranslations("common");
  const h = await getTranslations("hub");
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

  const { member, access, delegation, context, organization, roles } = result;
  const capabilities = context.capabilities;
  const csrfToken = (await readCsrfToken()) ?? "";
  const session = (await sessionCookieValue()) ?? "";
  const permissionMatrix = capabilities.includes("role.read")
    ? await apiRequest<CorporatePermissionMatrix>(
        `/v1/corporate/organizations/${organization.organization_id}/permissions/matrix`,
        { sessionToken: session },
      )
    : null;
  const grantableRoleNames = delegation?.grantable_roles.map((grantable) => grantable.name) ?? null;
  const { scopeOptions, currentScope, effective } = deriveAccessView(
    result,
    requestedScopeKind,
    requestedScopeId,
    t,
  );

  return (
    <div className="space-y-6">
      <HistoryBackButton label={h("backToAdmins")} fallback="/corporate/organization/admins" />
      <EmployeeHeader member={member} accountId={accountId} t={t} />

      <LocalizedResourceActions
        resource="members"
        resourceId={accountId}
        name={member.display_name ?? t("member")}
        role={member.role}
        state={member.state}
        revision={member.revision}
        organizationId={organization.organization_id}
        authorizationRevision={organization.authorization_revision}
        csrfToken={csrfToken}
        roles={roles?.items ?? []}
        permissions={capabilities}
        availableActions={capabilities}
      />

      <ScopeSelectForm
        options={scopeOptions}
        currentScope={currentScope}
        fallbackScope={`organization:${organization.organization_id}`}
        selectLabel={t("selectScope")}
        submitLabel={t("openAccess")}
      />

      <EffectiveDecisions effective={effective} t={t} />

      <section className="border-border bg-card rounded-lg border p-5 shadow-sm sm:p-6">
        <h2 className="text-xl font-medium">{t("accessAdministration")}</h2>
        <div className="mt-4">
          <CorporateMemberAccessPanel
            csrfToken={csrfToken}
            organizationId={organization.organization_id}
            authorizationRevision={organization.authorization_revision}
            accountId={accountId}
            teams={context.teams}
            projects={context.projects}
            roles={roles?.items ?? []}
            grantableRoleNames={grantableRoleNames}
            bindings={access?.bindings ?? []}
            grants={access?.grants ?? []}
            capabilities={capabilities}
            definitions={permissionMatrix?.definitions ?? []}
            labels={memberAccessLabels(t)}
          />
        </div>
      </section>

      <PrivateGrants grants={access?.private_grants ?? []} t={t} />
    </div>
  );
}

function EffectiveDecisions({
  effective,
  t,
}: {
  effective: readonly CorporateEffectivePermission[];
  t: (key: string) => string;
}) {
  return (
    <section className="border-border bg-card rounded-lg border p-5 shadow-sm sm:p-6">
      <h2 className="text-xl font-medium">{t("effectiveDecisions")}</h2>
      <p className="text-muted-foreground mt-1 text-sm">{t("effectiveDecisionsBody")}</p>
      {effective.length ? (
        <div className="-mx-4 mt-3 overflow-x-auto px-4 sm:-mx-5 sm:px-5">
          <Table className="min-w-max">
            <THead>
              <Tr>
                <Th scope="col" className="pl-0">
                  {t("permission")}
                </Th>
                <Th scope="col">{t("grantedBy")}</Th>
              </Tr>
            </THead>
            <TBody>
              {effective.map((item) => (
                <Tr key={item.permission} className="hover:bg-muted/40 transition-colors">
                  <Td className="pr-4 pl-0 font-mono text-xs whitespace-nowrap">
                    {item.permission}
                  </Td>
                  <Td>
                    <span className="inline-flex flex-wrap gap-1">
                      {item.source_records.length
                        ? item.source_records.map((source) => (
                            <Badge
                              key={source.source_id}
                              variant="secondary"
                              title={`${source.kind}:${source.source_id} · ${source.scope_kind}:${source.scope_id}`}
                            >
                              {source.role ?? source.kind}
                            </Badge>
                          ))
                        : item.sources.map((source) => (
                            <Badge key={source} variant="secondary">
                              {source}
                            </Badge>
                          ))}
                    </span>
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        </div>
      ) : (
        <p className="text-muted-foreground mt-3 text-sm">{t("noEffective")}</p>
      )}
    </section>
  );
}

function PrivateGrants({
  grants,
  t,
}: {
  grants: readonly CorporateMemberPrivateGrant[];
  t: (key: string) => string;
}) {
  return (
    <section className="border-border bg-card rounded-lg border p-5 shadow-sm sm:p-6">
      <h2 className="text-xl font-medium">{t("privateGrants")}</h2>
      {!grants.length ? (
        <p className="text-muted-foreground mt-3 text-sm">{t("noPrivateGrants")}</p>
      ) : null}
      <ul className="mt-3 space-y-2 text-sm">
        {grants.map((grant) => (
          <li
            key={grant.grant_id}
            className="border-border flex flex-wrap items-center justify-between gap-2 rounded border p-3"
          >
            <span className="font-mono text-xs">
              {grant.object_kind}:{grant.stable_id}@{grant.major}
            </span>
            <span className="text-muted-foreground text-xs">
              {t("issuer")} {grant.issuer_account_id} · {grant.state}
            </span>
          </li>
        ))}
      </ul>
    </section>
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

function ScopeSelectForm({
  options,
  currentScope,
  fallbackScope,
  selectLabel,
  submitLabel,
}: {
  options: readonly { value: string; label: string }[];
  currentScope: string;
  fallbackScope: string;
  selectLabel: string;
  submitLabel: string;
}) {
  return (
    <form method="get" className="flex flex-wrap items-end gap-2" aria-label={selectLabel}>
      <label htmlFor="access-scope" className="text-sm font-medium">
        {selectLabel}
      </label>
      <Select
        id="access-scope"
        name="scope"
        defaultValue={
          options.some((option) => option.value === currentScope) ? currentScope : fallbackScope
        }
        className="border-input bg-background focus-visible:ring-ring flex h-10 rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </Select>
      <Button type="submit" variant="outline" size="sm">
        {submitLabel}
      </Button>
    </form>
  );
}

function memberAccessLabels(t: (key: string) => string) {
  return {
    bindings: t("roleBindings"),
    team: t("team"),
    project: t("project"),
    role: t("role"),
    scope: t("scope"),
    organization: t("organization"),
    operation: t("operation"),
    assign: t("assign"),
    remove: t("remove"),
    create: t("create"),
    creating: t("creating"),
    revoke: t("revoke"),
    revoking: t("revoking"),
    coverage: t("coverage"),
    coverageSelf: t("coverageSelf"),
    coverageDescendants: t("coverageDescendants"),
    originMembership: t("originMembership"),
    originAssignment: t("originAssignment"),
    originDirect: t("originDirect"),
    originServicePrincipal: t("originServicePrincipal"),
    noBindings: t("noBindings"),
    directGrants: t("directGrants"),
    directGrantsBody: t("directGrantsBody"),
    grantAction: t("grantAction"),
    permission: t("permission"),
    issuer: t("issuer"),
    noGrants: t("noGrants"),
    saved: t("saved"),
    targetRequired: t("targetRequired"),
    assignments: t("assignments"),
    update: t("update"),
    confirmRevoke: t("confirmDelete"),
  };
}

type MemberAccessResult = Awaited<ReturnType<typeof readCorporateMemberAccess>>;

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

function EmployeeHeader({
  member,
  accountId,
  t,
}: {
  member: CorporateMember;
  accountId: string;
  t: (key: string) => string;
}) {
  return (
    <header className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-3xl font-medium tracking-tight">{t("employeeAccessTitle")}</h1>
        <Badge variant="secondary">{member.role}</Badge>
        {member.state !== "active" ? <Badge variant="warning">{member.state}</Badge> : null}
      </div>
      <Link
        href={`/corporate/employees/${accountId}`}
        className="text-muted-foreground text-sm underline underline-offset-4"
      >
        {member.display_name ?? t("member")}
      </Link>
      <p className="text-muted-foreground max-w-2xl text-sm">{t("employeeAccessBody")}</p>
    </header>
  );
}

function deriveAccessView(
  result: NonNullable<MemberAccessResult>,
  requestedScopeKind: string,
  requestedScopeId: string | undefined,
  t: (key: string) => string,
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
    ],
  };
}
