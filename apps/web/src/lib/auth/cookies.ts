/** Cookie names shared by Edge middleware and Node session code (ADR-0041). */
export const SESSION_COOKIE = "ai_stp_session";
export const CSRF_COOKIE = "ai_stp_csrf";
export const CORPORATE_ORG_COOKIE = "ai_stp_corporate_org";

/**
 * Invitation claim transport (#201): the emailed fragment token is parked in
 * an httpOnly cookie by the `hold` route, so it survives reloads and the
 * login round trip without ever being readable from JS — deliberately NOT
 * localStorage, where any same-origin script could exfiltrate bearer tokens.
 * A second JS-readable flag cookie marks "a claim is held" so the accept UI
 * can render the button on a fragment-less revisit.
 */
export type InvitationClaimVariant = "accept" | "confirm";

export const INVITATION_CLAIM_PATH_PREFIX = "/api/corporate/invitations/";

export function invitationClaimCookieName(
  invitationId: string,
  variant: InvitationClaimVariant,
): string {
  return `ai_stp_inv_${variant}_${invitationId}`;
}

export function invitationClaimFlagName(
  invitationId: string,
  variant: InvitationClaimVariant,
): string {
  return `ai_stp_invf_${variant}_${invitationId}`;
}

export function invitationClaimCookiePath(invitationId: string): string {
  return `${INVITATION_CLAIM_PATH_PREFIX}${invitationId}`;
}

/** Client-side check: was a claim token parked for this invitation+variant? */
export function hasInvitationClaimFlag(
  invitationId: string,
  variant: InvitationClaimVariant,
): boolean {
  if (typeof document === "undefined") {
    return false;
  }
  const name = `${invitationClaimFlagName(invitationId, variant)}=`;
  return document.cookie.split("; ").some((row) => row.startsWith(name));
}
