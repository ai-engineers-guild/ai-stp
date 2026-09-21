import {
  readCorporateCatalogOwnershipSummary,
  type CorporateCatalogOwnerMember,
} from "@/lib/api/corporate-catalog-ownership";
import { readOwnerObjectCapabilities } from "@/lib/api/owner";
import type { CorporateCatalogOwnerEdit } from "@/components/organisms/corporate-catalog-owner-editor";
import { asVersionId, tryAsComponentId, tryAsSetupId } from "@/lib/brands";

export type ObjectMenuProbe = {
  capabilities: string[];
  ownerEdit?: CorporateCatalogOwnerEdit;
};

export type ObjectMenuOrgContext = {
  organizationId: string;
  authorizationRevision: number;
  csrfToken: string;
  /** Member directory entries; loaded lazily by the page when any probe reports `edit`. */
  members: (() => Promise<CorporateCatalogOwnerMember[] | null>) | null;
};

function asMenuVersion(version: string | null | undefined) {
  try {
    return version ? asVersionId(version) : null;
  } catch {
    return null;
  }
}

/**
 * Resolves the capability-driven menu data for one catalog object: the
 * capabilities probe plus, when the caller may edit, the ownership record the
 * Edit dialog needs. Never throws; a failed probe yields viewer-only actions.
 */
export async function probeObjectMenu(
  sessionToken: string,
  objectKind: "component" | "setup",
  stableId: string,
  version: string | null,
  org?: ObjectMenuOrgContext,
): Promise<ObjectMenuProbe> {
  const probe = await readOwnerObjectCapabilities(sessionToken, objectKind, stableId).catch(
    () => null,
  );
  const capabilities = probe?.capabilities ?? [];
  if (!capabilities.includes("edit") || !org?.members) return { capabilities };
  const menuVersion = asMenuVersion(version);
  const typedId = objectKind === "component" ? tryAsComponentId(stableId) : tryAsSetupId(stableId);
  if (!menuVersion || !typedId) return { capabilities };
  const ownership = await readCorporateCatalogOwnershipSummary(
    sessionToken,
    org.organizationId,
    objectKind,
    typedId,
    menuVersion,
  ).catch(() => null);
  if (!ownership?.can_edit) return { capabilities };
  const members = await org.members();
  if (!members) return { capabilities };
  return {
    capabilities,
    ownerEdit: {
      ownership,
      objectKind,
      stableId,
      version: menuVersion,
      organizationId: org.organizationId,
      authorizationRevision: org.authorizationRevision,
      csrfToken: org.csrfToken,
      members,
    },
  };
}
