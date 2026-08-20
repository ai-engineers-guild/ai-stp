import { apiRequest } from "@/lib/api/http";
import type { AccountId } from "@/lib/brands";
import { ALL_COMPONENT_SUMMARIES, ALL_SETUP_SUMMARIES, seedPublicProfiles } from "@/mocks/fixtures";

import type {
  AccountPrivacyUpdate,
  AccountProfile,
  ComponentSummary,
  SetupSummary,
} from "./generated/types.gen";

/**
 * Public publisher profile is documented in docs/contracts/public-profile.md
 * but is not yet an OpenAPI path in the frozen #71 surface. Mock-first web
 * serves a local projection for `/publishers/[account]` (REQ-2210).
 */
export type PublicProfileView = {
  account_id: AccountId;
  display_name: string | null;
  bio: string | null;
  links: ReadonlyArray<{ label: string; url: string }>;
};

export type PublisherObjects = {
  components: ReadonlyArray<ComponentSummary>;
  setups: ReadonlyArray<SetupSummary>;
};

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

/**
 * Public profile projection — allowlist fields only, no device data (REQ-2210).
 * Seed authors return first-party profiles; unknown accounts return empty fields.
 */
export function readPublicProfile(accountId: AccountId): PublicProfileView {
  if (accountId in seedPublicProfiles) {
    const profile = seedPublicProfiles[accountId as keyof typeof seedPublicProfiles];
    return {
      account_id: accountId,
      display_name: profile.display_name,
      bio: profile.bio,
      links: profile.links,
    };
  }
  return {
    account_id: accountId,
    display_name: null,
    bio: null,
    links: [],
  };
}

/** Published catalog objects owned by the account (seed multi-author corpus). */
export function listPublisherObjects(accountId: AccountId): PublisherObjects {
  return {
    components: ALL_COMPONENT_SUMMARIES.filter((item) => item.owner_id === accountId),
    setups: ALL_SETUP_SUMMARIES.filter((item) => item.owner_id === accountId),
  };
}

/** @deprecated use readPublicProfile */
export function mockPublicProfile(accountId: AccountId): PublicProfileView {
  return readPublicProfile(accountId);
}
