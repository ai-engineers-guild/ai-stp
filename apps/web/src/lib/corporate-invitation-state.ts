import type { CorporateInvitation } from "@/lib/api/generated/types.gen";

export function isOutstandingInvitation(
  invitation: CorporateInvitation,
  now = Date.now(),
): boolean {
  return (
    ["pending", "email_confirm_pending"].includes(invitation.state) &&
    Date.parse(invitation.expires_at) > now
  );
}

export function invitationDisplayState(invitation: CorporateInvitation, now: number) {
  return ["pending", "email_confirm_pending"].includes(invitation.state) &&
    Date.parse(invitation.expires_at) <= now
    ? "expired"
    : invitation.state;
}
