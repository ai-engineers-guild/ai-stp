import { apiRequest, apiRequestWithMeta } from "@/lib/api/http";
import type { ExternalProduct } from "@/lib/api/catalog";
import type {
  OwnerObjectDetail,
  OwnerObjectListResponse,
  OwnerVersionDetail,
  PublicationPlanResponse,
} from "@/lib/api/generated/types.gen";

export type OwnerPresentationMedia = {
  kind: "image" | "video" | "youtube";
  url: string;
  alt: string;
  caption: string;
};

export type OwnerPresentation = {
  schema_version: 1;
  stable_id: string;
  bio: string;
  media: OwnerPresentationMedia[];
};

export async function listOwnerObjects(
  sessionToken: string,
  query?: { object_kind?: "component" | "setup"; page_size?: number },
): Promise<OwnerObjectListResponse> {
  return apiRequest<OwnerObjectListResponse>("/v1/owner/objects", {
    sessionToken,
    query: {
      schema_version: 1,
      page_size: query?.page_size ?? 20,
      object_kind: query?.object_kind,
    },
  });
}

export async function readOwnerObject(
  sessionToken: string,
  objectKind: "component" | "setup",
  stableId: string,
): Promise<OwnerObjectDetail> {
  return apiRequest<OwnerObjectDetail>(`/v1/owner/objects/${objectKind}/${stableId}`, {
    sessionToken,
  });
}

export async function readOwnerPresentation(
  sessionToken: string,
  stableId: string,
): Promise<OwnerPresentation> {
  return apiRequest<OwnerPresentation>(`/v1/owner/objects/component/${stableId}/presentation`, {
    sessionToken,
  });
}

export async function updateOwnerPresentation(
  sessionToken: string,
  stableId: string,
  body: Pick<OwnerPresentation, "bio" | "media">,
): Promise<OwnerPresentation> {
  return apiRequest<OwnerPresentation>(`/v1/owner/objects/component/${stableId}/presentation`, {
    method: "PUT",
    sessionToken,
    body: { schema_version: 1, ...body },
  });
}

export async function readOwnerExternalProducts(
  sessionToken: string,
  objectKind: "component" | "setup",
  stableId: string,
): Promise<{ schema_version: 1; items: ExternalProduct[] }> {
  return apiRequest(`/v1/owner/objects/${objectKind}/${stableId}/external-products`, {
    sessionToken,
  });
}

export async function replaceOwnerExternalProducts(
  sessionToken: string,
  objectKind: "component" | "setup",
  stableId: string,
  canonicalDomains: string[],
): Promise<{ schema_version: 1; items: ExternalProduct[] }> {
  return apiRequest(`/v1/owner/objects/${objectKind}/${stableId}/external-products`, {
    method: "PUT",
    sessionToken,
    body: { schema_version: 1, canonical_domains: canonicalDomains },
  });
}

export async function readOwnerVersion(
  sessionToken: string,
  objectKind: "component" | "setup",
  stableId: string,
  version: string,
): Promise<OwnerVersionDetail> {
  return apiRequest<OwnerVersionDetail>(
    `/v1/owner/objects/${objectKind}/${stableId}/versions/${version}`,
    { sessionToken },
  );
}

export async function startOwnerPublication(
  sessionToken: string,
  objectKind: "component" | "setup",
  stableId: string,
  version: string,
  body: {
    device_id: string;
    idempotency_key: string;
    policy_version?: string;
  },
): Promise<{ body: PublicationPlanResponse; operationId: string | null }> {
  const result = await apiRequestWithMeta<PublicationPlanResponse>(
    `/v1/owner/objects/${objectKind}/${stableId}/versions/${version}/publication-plans`,
    {
      method: "POST",
      sessionToken,
      body: {
        schema_version: 1,
        device_id: body.device_id,
        idempotency_key: body.idempotency_key,
        policy_version: body.policy_version ?? "1",
      },
    },
  );
  return { body: result.data, operationId: result.operationId };
}
