import { apiRequest } from "@/lib/api/http";

import type {
  CorporateDistributionRequest,
  CorporateDistributionResult,
  CorporateDistributionStateList,
  CorporateEffectiveAssignment,
} from "./generated/types.gen";

export async function readEffectiveCorporateAssignment(
  sessionToken: string,
  organizationId: string,
  query: {
    account_id: string;
    object_kind: "setup" | "component";
    stable_id: string;
    project_id?: string;
    technology_id?: string;
    harness?: string;
  },
): Promise<CorporateEffectiveAssignment> {
  return apiRequest<CorporateEffectiveAssignment>(
    `/v1/corporate/organizations/${organizationId}/catalog-assignments/effective`,
    {
      sessionToken,
      query: {
        account_id: query.account_id,
        object_kind: query.object_kind,
        stable_id: query.stable_id,
        project_id: query.project_id,
        technology_id: query.technology_id,
        harness: query.harness,
      },
    },
  );
}

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
