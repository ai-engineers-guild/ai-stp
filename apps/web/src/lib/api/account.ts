import { apiRequest } from "@/lib/api/http";

import type { AccountPrivacyUpdate, AccountProfile } from "./generated/types.gen";

export async function readAccount(sessionToken: string): Promise<AccountProfile> {
  return apiRequest<AccountProfile>("/v1/account", { sessionToken });
}

export async function updateAccountPrivacy(
  preferences: AccountPrivacyUpdate,
  sessionToken: string,
): Promise<AccountProfile> {
  return apiRequest<AccountProfile>("/v1/account/privacy", {
    method: "PUT",
    body: preferences,
    sessionToken,
  });
}

export type UnlinkProvider = "google" | "github";

/** Unlink one OAuth identity. Fails when it would leave the account with none. */
export async function unlinkAccountIdentity(
  provider: UnlinkProvider,
  sessionToken: string,
): Promise<AccountProfile> {
  return apiRequest<AccountProfile>(`/v1/account/identities/${provider}`, {
    method: "DELETE",
    sessionToken,
  });
}

/**
 * Privacy fields present on the frozen AccountProfile model (design #83):
 * none beyond identities linkage metadata. Surface only what the contract has.
 */
export function privacyFieldsFromAccount(profile: AccountProfile) {
  return {
    showProfilePublicly: profile.show_profile_publicly,
    allowPublisherListing: profile.allow_publisher_listing,
  };
}
