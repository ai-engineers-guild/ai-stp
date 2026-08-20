import { apiRequest, apiRequestWithMeta } from "@/lib/api/http";
import type { PublicationPlanResponse } from "@/lib/api/generated/types.gen";

export async function readPublicationPlan(
  sessionToken: string,
  planId: string,
): Promise<PublicationPlanResponse> {
  return apiRequest<PublicationPlanResponse>(`/v1/publications/plans/${planId}`, {
    sessionToken,
  });
}

export async function confirmPublicationPlan(
  sessionToken: string,
  planId: string,
  planHash: string,
  idempotencyKey: string,
): Promise<{ body: PublicationPlanResponse; operationId: string | null }> {
  const result = await apiRequestWithMeta<PublicationPlanResponse>(
    `/v1/publications/plans/${planId}/confirm`,
    {
      method: "POST",
      sessionToken,
      body: {
        schema_version: 1,
        plan_hash: planHash,
        confirmed: true,
        idempotency_key: idempotencyKey,
      },
    },
  );
  return { body: result.data, operationId: result.operationId };
}
