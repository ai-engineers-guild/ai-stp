"use server";

import { apiRequest } from "@/lib/api/http";
import { readCorporateOrganization } from "@/lib/api/corporate";
import type { EntityActionMenus, EntityActionSubject } from "@/lib/api/generated/types.gen";
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
