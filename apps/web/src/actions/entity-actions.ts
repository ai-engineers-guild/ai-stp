"use server";

import { apiRequest } from "@/lib/api/http";
import { readCorporateOrganization } from "@/lib/api/corporate";
import type {
  EntityActionMenus,
  EntityActionSubject,
  CorporatePermissionMatrix,
} from "@/lib/api/generated/types.gen";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export async function loadEntityActionMenus(subjects: EntityActionSubject[]): Promise<{
  menus: EntityActionMenus;
  csrfToken: string;
}> {
  const token = await sessionCookieValue();
  const needsOrganization = subjects.some(
    (subject) => !["grant", "publisher"].includes(subject.kind) && !subject.organization_id,
  );
  const organization = needsOrganization && token ? await readCorporateOrganization(token) : null;
  const menus = await apiRequest<EntityActionMenus>("/v1/entity-actions/query", {
    method: "POST",
    ...(token ? { sessionToken: token } : {}),
    body: {
      schema_version: 1,
      subjects: subjects.map((subject) => ({
        ...subject,
        ...(!["grant", "publisher"].includes(subject.kind) &&
        !subject.organization_id &&
        organization
          ? { organization_id: organization.organization_id }
          : {}),
      })),
    },
  });
  return { menus, csrfToken: (await readCsrfToken()) ?? "" };
}

export async function loadCatalogOwnerEditor(subject: EntityActionSubject, version: string) {
  const token = await sessionCookieValue();
  if (!token || !subject.organization_id || !["component", "setup"].includes(subject.kind))
    throw new Error("invalid ownership context");
  const { readCorporateCatalogOwnership } = await import("@/lib/api/corporate-catalog-ownership");
  const { asVersionId, tryAsComponentId, tryAsSetupId } = await import("@/lib/brands");
  const objectKind = subject.kind as "component" | "setup";
  const stableId =
    objectKind === "component" ? tryAsComponentId(subject.id) : tryAsSetupId(subject.id);
  if (!stableId) throw new Error("invalid catalog identity");
  const data = await readCorporateCatalogOwnership(
    token,
    objectKind,
    stableId,
    asVersionId(version),
  );
  if (
    !data?.ownership.can_edit ||
    !data.members ||
    data.ownership.organization_id !== subject.organization_id
  )
    throw new Error("ownership context unavailable");
  return {
    ownership: data.ownership,
    objectKind,
    stableId: subject.id,
    version,
    organizationId: subject.organization_id,
    authorizationRevision: data.authorizationRevision,
    csrfToken: (await readCsrfToken()) ?? "",
    members: data.members,
  };
}

export async function loadTechnologyOwnerEditor(subject: EntityActionSubject) {
  const token = await sessionCookieValue();
  if (!token || subject.kind !== "technology" || !subject.organization_id)
    throw new Error("invalid ownership context");
  const { menus } = await loadEntityActionMenus([subject]);
  if (!menus.items[0]?.actions.some((action) => action.id === "change_owner"))
    throw new Error("ownership unavailable");
  const { readCorporatePresentation } = await import("@/lib/api/corporate-detail");
  const { readCorporateWorkspace } = await import("@/lib/api/corporate");
  const [workspace, presentation] = await Promise.all([
    readCorporateWorkspace(token, false),
    readCorporatePresentation(
      token,
      subject.organization_id,
      "technologies",
      subject.id,
      menus.items[0].authorization_revision ?? 0,
    ),
  ]);
  if (
    !workspace ||
    !presentation ||
    workspace.organization.organization_id !== subject.organization_id
  )
    throw new Error("ownership unavailable");
  return {
    presentation,
    members: workspace.members?.items ?? [],
    csrfToken: (await readCsrfToken()) ?? "",
  };
}

function settledValue<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === "fulfilled" ? result.value : fallback;
}

export async function loadCorporateGrantDialog(subject: EntityActionSubject) {
  const token = await sessionCookieValue();
  if (!token || !subject.organization_id) throw new Error("invalid grant context");
  const { menus } = await loadEntityActionMenus([subject]);
  if (!menus.items[0]?.actions.some((action) => action.id === "manage_access"))
    throw new Error("grant unavailable");
  const {
    readCorporateWorkspace,
    readCorporateMemberAccess,
    readCorporateCatalogScopeOptions,
    readCorporateCategoryScopeOptions,
    readCorporateScopeTechnologies,
  } = await import("@/lib/api/corporate");
  const workspace = await readCorporateWorkspace(token, false);
  if (!workspace || workspace.organization.organization_id !== subject.organization_id)
    throw new Error("grant unavailable");
  const org = subject.organization_id;
  const caps = workspace.context.capabilities;
  const [accessResult, matrixResult, technologiesResult, catalogResult, categoriesResult] =
    await Promise.allSettled([
      subject.kind === "member" ? readCorporateMemberAccess(token, subject.id) : null,
      caps.includes("role.read")
        ? apiRequest<CorporatePermissionMatrix>(
            `/v1/corporate/organizations/${org}/permissions/matrix`,
            { sessionToken: token },
          )
        : null,
      readCorporateScopeTechnologies(token, org, caps),
      readCorporateCatalogScopeOptions(token, org, caps),
      readCorporateCategoryScopeOptions(token, org, caps),
    ]);
  const access = settledValue(accessResult, null);
  const matrix = settledValue(matrixResult, null);
  const technologies = settledValue(technologiesResult, []);
  const catalog = settledValue(catalogResult, []);
  const categories = settledValue(categoriesResult, []);
  const scopeOptions = [
    ...technologies.map((item) => ({ value: `technology:${item.id}`, label: item.name })),
    ...catalog,
    ...categories,
  ];
  const targetScope = `catalog_object:${subject.id}`;
  if (subject.kind !== "member" && !scopeOptions.some((option) => option.value === targetScope))
    scopeOptions.unshift({ value: targetScope, label: menus.items[0].object_name ?? subject.id });
  return {
    csrfToken: (await readCsrfToken()) ?? "",
    organizationId: org,
    authorizationRevision: workspace.context.organization.authorization_revision,
    members: workspace.members?.items ?? (access ? [access.member] : []),
    initialMemberIds: subject.kind === "member" ? [subject.id] : [],
    initialScope: subject.kind === "member" ? undefined : `catalog_object:${subject.id}`,
    roles: workspace.roles?.items ?? [],
    grantableRoleNames: access?.delegation?.grantable_roles.map((role) => role.name) ?? null,
    teams: workspace.context.teams,
    projects: workspace.context.projects,
    capabilities: caps,
    definitions: matrix?.definitions ?? [],
    scopeOptions,
  };
}
