import { apiRequest, apiRequestWithMeta } from "@/lib/api/http";
import type {
  AccessGrantResponse,
  GrantInvitationResponse,
  GrantListResponse,
  GrantRevokeResponse,
} from "@/lib/api/generated/types.gen";

export async function listGrants(sessionToken: string): Promise<GrantListResponse> {
  return apiRequest<GrantListResponse>("/v1/grants", { sessionToken });
}

export async function createGrantInvitation(
  sessionToken: string,
  body: {
    object_kind: "component" | "setup";
    stable_id: string;
    major: number;
    recipient_email: string;
    idempotency_key: string;
  },
): Promise<{ body: GrantInvitationResponse; operationId: string | null }> {
  const result = await apiRequestWithMeta<GrantInvitationResponse>("/v1/grants/invitations", {
    method: "POST",
    sessionToken,
    body: {
      schema_version: 1,
      ...body,
      ttl_seconds: 604_800,
    },
  });
  return { body: result.data, operationId: result.operationId };
}

export async function createDirectGrant(
  sessionToken: string,
  body: {
    object_kind: "component" | "setup";
    stable_id: string;
    major: number;
    recipient_kind: "github_username" | "user_id";
    recipient: string;
    idempotency_key: string;
  },
): Promise<{ body: AccessGrantResponse; operationId: string | null }> {
  const result = await apiRequestWithMeta<AccessGrantResponse>("/v1/grants/direct", {
    method: "POST",
    sessionToken,
    body: { schema_version: 1, ...body },
  });
  return { body: result.data, operationId: result.operationId };
}

export async function acceptGrantInvitation(
  sessionToken: string,
  invitationId: string,
  token: string,
  idempotencyKey: string,
): Promise<{ body: AccessGrantResponse; operationId: string | null }> {
  const result = await apiRequestWithMeta<AccessGrantResponse>(
    `/v1/grants/invitations/${invitationId}/accept`,
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

export async function revokeGrantInvitation(
  sessionToken: string,
  invitationId: string,
  reason: string,
  idempotencyKey: string,
): Promise<{ body: GrantRevokeResponse; operationId: string | null }> {
  const result = await apiRequestWithMeta<GrantRevokeResponse>(
    `/v1/grants/invitations/${invitationId}/revoke`,
    {
      method: "POST",
      sessionToken,
      body: {
        schema_version: 1,
        reason,
        idempotency_key: idempotencyKey,
      },
    },
  );
  return { body: result.data, operationId: result.operationId };
}

export async function revokeAccessGrant(
  sessionToken: string,
  grantId: string,
  reason: string,
  idempotencyKey: string,
): Promise<{ body: GrantRevokeResponse; operationId: string | null }> {
  const result = await apiRequestWithMeta<GrantRevokeResponse>(`/v1/grants/${grantId}/revoke`, {
    method: "POST",
    sessionToken,
    body: {
      schema_version: 1,
      reason,
      idempotency_key: idempotencyKey,
    },
  });
  return { body: result.data, operationId: result.operationId };
}
