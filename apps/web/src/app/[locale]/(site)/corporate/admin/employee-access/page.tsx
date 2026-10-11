import { getTranslations, setRequestLocale } from "next-intl/server";
import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateMembersDirectory } from "@/components/organisms/corporate-members-directory";
import {
  readCorporateWorkspace,
  readCorporateCatalogScopeOptions,
  readCorporateCategoryScopeOptions,
  readCorporateScopeTechnologies,
} from "@/lib/api/corporate";
import { apiRequest } from "@/lib/api/http";
import { ApiError } from "@/lib/api/errors";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { PeopleHeader } from "@/app/[locale]/(site)/corporate/admin/people-shared";
import type {
  CorporateContext,
  CorporateDelegationView,
  CorporatePermissionMatrix,
} from "@/lib/api/generated/types.gen";
import { EmployeeAccessView } from "./employee-access-view";

/**
 * Everything the Grant access dialog needs: permission definitions for the
 * scoped permission picker, the delegation bounds for the role picker, and
 * every scope option the API accepts.
 */
async function loadGrantAccessData(
  session: string,
  organizationId: string,
  capabilities: readonly string[],
  context: CorporateContext,
) {
  const [matrix, delegation, technologies, catalogScopes, categoryScopes] = await Promise.all([
    capabilities.includes("role.read")
      ? apiRequest<CorporatePermissionMatrix>(
          `/v1/corporate/organizations/${organizationId}/permissions/matrix`,
          { sessionToken: session },
        ).catch(() => null)
      : Promise.resolve(null),
    apiRequest<CorporateDelegationView>(
      `/v1/corporate/organizations/${organizationId}/delegation`,
      { sessionToken: session },
    ).catch(() => null),
    readCorporateScopeTechnologies(session, organizationId, capabilities),
    readCorporateCatalogScopeOptions(session, organizationId, capabilities),
    readCorporateCategoryScopeOptions(session, organizationId, capabilities),
  ]);
  return {
    grantableRoleNames: delegation?.grantable_roles.map((grantable) => grantable.name) ?? null,
    definitions: matrix?.definitions ?? [],
    scopeOptions: [
      ...context.teams.map((team) => ({
        value: `team:${team.team_id}`,
        label: team.name,
      })),
      ...context.projects.map((project) => ({
        value: `project:${project.project_id}`,
        label: project.name,
      })),
      ...technologies.map((item) => ({ value: `technology:${item.id}`, label: item.name })),
      ...catalogScopes,
      ...categoryScopes,
    ],
  };
}

export default async function EmployeeAccessPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  const filters = await searchParams;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/admin/employee-access`);
  const h = await getTranslations("hub");
  const t = await getTranslations("accessUi");
  const common = await getTranslations("common");
  let workspace: Awaited<ReturnType<typeof readCorporateWorkspace>>;
  try {
    workspace = await readCorporateWorkspace((await sessionCookieValue()) ?? "", false);
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE")
      return (
        <StatePanel kind="error" title={common("error")} description={common("apiUnavailable")} />
      );
    throw error;
  }

  if (
    !workspace ||
    !canViewCorporateAdministration(workspace.context.capabilities) ||
    !workspace.context.capabilities.includes("member.list")
  )
    return <StatePanel kind="error" title={h("employeeAccess")} description={t("forbidden")} />;
  const members = workspace.members?.items ?? [];
  const employee = members.find((member) => member.account_id === filters.employee);
  const session = await sessionCookieValue();
  const grantAccess = await loadGrantAccessData(
    session ?? "",
    workspace.organization.organization_id,
    workspace.context.capabilities,
    workspace.context,
  );
  return (
    <div className="min-w-0 space-y-5">
      <PeopleHeader
        section={h("peopleAndAccess")}
        current={h("employeeAccess")}
        description={t("employeeBody")}
      />
      <CorporateMembersDirectory
        accessView
        members={members}
        context={workspace.context}
        roles={workspace.roles?.items ?? []}
        jobTitles={workspace.jobTitles?.items ?? []}
        bindings={workspace.bindings?.items ?? []}
        csrfToken={(await readCsrfToken()) ?? ""}
        now={new Date().toISOString()}
        grantAccess={grantAccess}
        accessPanel={
          employee ? <EmployeeAccessView accountId={employee.account_id} filters={filters} /> : null
        }
      />
    </div>
  );
}
