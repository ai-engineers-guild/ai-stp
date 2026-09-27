import { apiRequest, apiRequestWithMeta } from "@/lib/api/http";
import type {
  CorporateInvitationList,
  CorporateMember,
  CorporateMembershipPolicy,
} from "@/lib/api/generated/types.gen";

export async function listCorporateInvitations(
  sessionToken: string,
  organizationId: string,
): Promise<CorporateInvitationList> {
  return apiRequest<CorporateInvitationList>(
    `/v1/corporate/organizations/${organizationId}/invitations`,
    { sessionToken },
  );
}

export async function readCorporateMembershipPolicy(
  sessionToken: string,
  organizationId: string,
): Promise<CorporateMembershipPolicy> {
  return apiRequest<CorporateMembershipPolicy>(
    `/v1/corporate/organizations/${organizationId}/membership/policy`,
    { sessionToken },
  );
}

export async function acceptCorporateInvitation(
  sessionToken: string,
  invitationId: string,
  token: string,
  idempotencyKey: string,
): Promise<{ body: CorporateMember; operationId: string | null }> {
  const result = await apiRequestWithMeta<CorporateMember>(
    `/v1/corporate/invitations/${invitationId}/accept`,
    {
      method: "POST",
      sessionToken,
      body: {
        schema_version: 1,
        token,
        idempotency_key: idempotencyKey,
      },
    },
  );
  return { body: result.data, operationId: result.operationId };
}
