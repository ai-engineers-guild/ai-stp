import { apiRequest } from "@/lib/api/http";

import type {
  CorporateAssignmentPlan,
  CorporateAssignmentPlanRequest,
  CorporateDistributionRequest,
  CorporateDistributionResult,
  CorporateDistributionStateList,
} from "./generated/types.gen";

export async function distributeCorporateAssignment(
  sessionToken: string,
  organizationId: string,
  request: CorporateDistributionRequest,
): Promise<CorporateDistributionResult> {
  return apiRequest<CorporateDistributionResult>(
    `/v1/corporate/organizations/${organizationId}/catalog-assignments/distribution`,
    {
      sessionToken,
      method: "POST",
      body: request,
    },
  );
}

export async function readCorporateAssignmentDistribution(
  sessionToken: string,
  organizationId: string,
  query: {
    source_assignment_id: string;
    offset?: number;
    limit?: number;
  },
): Promise<CorporateDistributionStateList> {
  return apiRequest<CorporateDistributionStateList>(
    `/v1/corporate/organizations/${organizationId}/catalog-assignments/distribution`,
    {
      sessionToken,
      query: {
        source_assignment_id: query.source_assignment_id,
        offset: query.offset === undefined ? undefined : String(query.offset),
        limit: query.limit === undefined ? undefined : String(query.limit),
      },
    },
  );
}

export async function planCorporateAssignment(
  sessionToken: string,
  organizationId: string,
  request: CorporateAssignmentPlanRequest,
): Promise<CorporateAssignmentPlan> {
  return apiRequest<CorporateAssignmentPlan>(
    `/v1/corporate/organizations/${organizationId}/catalog-assignments/plan`,
    {
      sessionToken,
      method: "POST",
      body: request,
    },
  );
}
