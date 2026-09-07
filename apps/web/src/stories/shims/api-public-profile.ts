/** In-process profile actions for Storybook; no server cookies or network. */
import { profileHandlers } from "@/lib/api/mock-profile";
import type { OwnerPublicProfile, ProfileFields } from "@/lib/api/public-profile";

export async function saveOwnerPublicProfileDraft(
  _csrfToken: string,
  body: ProfileFields,
  _ifMatch: string | null,
): Promise<OwnerPublicProfile> {
  return profileHandlers("PUT", "/v1/account/public-profile/draft", "story-session", body)
    ?.body as OwnerPublicProfile;
}

export async function publishOwnerPublicProfile(_csrfToken: string, _digest: string) {
  return { operation_id: "story_publish", published: true };
}

export async function importAvatarFromIdentity(_csrfToken: string, _provider: "github" | "google") {
  return {
    ok: true as const,
    avatar: { avatar_asset_id: "avatar_story", public_url: "/brand/icon-32.png" },
  };
}
