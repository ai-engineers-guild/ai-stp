import type { AccessGrantResponse } from "@/lib/api/generated/types.gen";

export type GrantRecipientInput = {
  recipientKind: "verified_email" | "github_username" | "user_id";
  recipient: string;
  kind: "component" | "setup";
  stableId: string;
  major: number;
};

export function grantPreconditions(
  grants: readonly AccessGrantResponse[],
  input: GrantRecipientInput,
) {
  const recipient = input.recipient.trim();
  const observed = grants.find(
    (grant) =>
      grant.object_kind === input.kind &&
      grant.stable_id === input.stableId &&
      grant.major === input.major &&
      (input.recipientKind === "user_id"
        ? grant.grantee_account_id === recipient
        : input.recipientKind === "github_username" &&
          grant.recipient_kind === "github_username" &&
          grant.recipient === recipient.toLowerCase().replace(/^@/, "")),
  );
  return {
    expectedGrantId: observed?.revision ? observed.grant_id : undefined,
    expectedRevision: observed?.revision ?? undefined,
    idempotencyKey: crypto.randomUUID(),
  };
}
