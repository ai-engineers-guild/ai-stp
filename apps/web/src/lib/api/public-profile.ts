"use server";

import { apiRequest } from "@/lib/api/http";
import { publicApiGet } from "@/lib/api/public-http";
import type { AccountId } from "@/lib/brands";

export type ProfileLink = { label: string; url: string };

export type ProfileFields = {
  display_name: string | null;
  bio: string | null;
  links: ProfileLink[];
  avatar_asset_id: string | null;
};

export type PublicProfileProjection = {
  schema_version: number;
  kind: "public_profile";
  account_id: string;
  display_name: string | null;
  bio: string | null;
  links: ReadonlyArray<ProfileLink>;
  avatar_url: string | null;
  author_verified: boolean;
  empty?: boolean;
};

export type OwnerPublicProfile = {
  schema_version: number;
  account_id: string;
  state: string;
  editable: {
    source: "draft" | "published" | "empty";
    base_revision_id: string | null;
    base_content_digest: string | null;
    fields: ProfileFields;
    avatar_url: string | null;
  };
  draft: {
    revision_id: string | null;
    content_digest: string | null;
    fields: ProfileFields;
    avatar_url: string | null;
  };
  published: {
    revision_id: string;
    content_digest: string;
    fields: ProfileFields;
    avatar_url: string | null;
    projection: PublicProfileProjection;
  } | null;
};

export type OwnerPreview = {
  schema_version: number;
  preview: true;
  lifecycle: string;
  content_digest: string;
  projection: PublicProfileProjection;
};

export async function readOwnerPublicProfile(sessionToken: string): Promise<OwnerPublicProfile> {
  return apiRequest<OwnerPublicProfile>("/v1/account/public-profile", { sessionToken });
}

export async function saveOwnerPublicProfileDraft(
  sessionToken: string,
  body: {
    display_name: string | null;
    bio: string | null;
    links: ProfileLink[];
    avatar_asset_id: string | null;
  },
  ifMatch?: string | null,
): Promise<OwnerPublicProfile> {
  const options: {
    method: "PUT";
    sessionToken: string;
    body: typeof body;
    headers?: Record<string, string>;
  } = {
    method: "PUT",
    sessionToken,
    body,
  };
  if (ifMatch) {
    options.headers = { "If-Match": ifMatch };
  }
  return apiRequest<OwnerPublicProfile>("/v1/account/public-profile/draft", options);
}

export async function publishOwnerPublicProfile(
  sessionToken: string,
  contentDigest: string,
): Promise<{ operation_id: string; published: boolean }> {
  const idempotencyKey = crypto.randomUUID();
  return apiRequest("/v1/account/public-profile/publish", {
    method: "POST",
    sessionToken,
    headers: { "Idempotency-Key": idempotencyKey },
    body: { content_digest: contentDigest },
  });
}

export async function previewOwnerPublicProfile(sessionToken: string): Promise<OwnerPreview> {
  return apiRequest<OwnerPreview>("/v1/account/public-profile/preview", { sessionToken });
}

export async function registerAvatarUpload(
  sessionToken: string,
  file: File | Blob,
  contentType: string,
): Promise<{ avatar_asset_id: string; public_url: string | null; object_key?: string }> {
  // Binary body goes through raw fetch so we can set Content-Type image/* (not JSON).
  const { apiRequestBinary } = await import("@/lib/api/http");
  return apiRequestBinary("/v1/account/public-profile/avatar", {
    method: "POST",
    sessionToken,
    contentType,
    body: file,
  });
}

export async function importAvatarFromIdentity(
  sessionToken: string,
  provider: "github" | "google",
): Promise<{ avatar_asset_id: string; public_url: string | null }> {
  return apiRequest("/v1/account/public-profile/avatar/from-identity", {
    method: "POST",
    sessionToken,
    body: { provider },
  });
}

export async function readPublisherProfile(accountId: AccountId): Promise<PublicProfileProjection> {
  return publicApiGet<PublicProfileProjection>(`/v1/publishers/${accountId}`);
}
