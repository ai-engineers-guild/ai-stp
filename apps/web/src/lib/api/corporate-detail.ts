import { ApiError } from "./errors";
import { apiRequest } from "./http";
import {
  corporatePresentationPath,
  presentationFromProfile,
  type CorporateDetailResource,
} from "@/lib/corporate-detail";

export async function readCorporatePresentation(
  sessionToken: string,
  organizationId: string,
  resource: CorporateDetailResource,
  id: string,
  authorizationRevision: number,
) {
  try {
    return presentationFromProfile(
      await apiRequest<unknown>(corporatePresentationPath(organizationId, resource, id), {
        sessionToken,
      }),
      authorizationRevision,
    );
  } catch (error) {
    // A missing optional profile falls back to the incumbent entity description.
    // Availability failures must remain visible instead of looking like an empty profile.
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
