"use server";

import { assertCsrf, readCsrfToken } from "@/lib/auth/session";
import { sessionCookieValue } from "@/lib/auth/require-session";

import { ApiError, type ApiErrorCode } from "./errors";
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

async function profileMutationSession(csrfToken: string): Promise<string> {
  assertCsrf(csrfToken, await readCsrfToken());
  const token = await sessionCookieValue();
  if (!token) throw new Error("not signed in");
  return token;
}

export async function readOwnerPublicProfile(sessionToken: string): Promise<OwnerPublicProfile> {
  return apiRequest<OwnerPublicProfile>("/v1/account/public-profile", { sessionToken });
}

export async function saveOwnerPublicProfileDraft(
  csrfToken: string,
  body: {
    display_name: string | null;
    bio: string | null;
    links: ProfileLink[];
    avatar_asset_id: string | null;
  },
  ifMatch?: string | null,
): Promise<OwnerPublicProfile> {
  const sessionToken = await profileMutationSession(csrfToken);
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
  csrfToken: string,
  contentDigest: string,
): Promise<{ operation_id: string; published: boolean }> {
  const sessionToken = await profileMutationSession(csrfToken);
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
  csrfToken: string,
  file: File | Blob,
  contentType: string,
): Promise<{ avatar_asset_id: string; public_url: string | null }> {
  const sessionToken = await profileMutationSession(csrfToken);
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
  csrfToken: string,
  provider: "github" | "google",
): Promise<
  | { ok: true; avatar: { avatar_asset_id: string; public_url: string | null } }
  | { ok: false; code: ApiErrorCode; message: string; status: number }
> {
  try {
    const sessionToken = await profileMutationSession(csrfToken);
    const avatar = await apiRequest<{ avatar_asset_id: string; public_url: string | null }>(
      "/v1/account/public-profile/avatar/from-identity",
      { method: "POST", sessionToken, body: { provider } },
    );
    return { ok: true, avatar };
  } catch (error) {
    return error instanceof ApiError
      ? { ok: false, code: error.code, message: error.message, status: error.status }
      : {
          ok: false,
          code: "AI_STP_UNAUTHORIZED",
          message: "Reload the page and sign in again.",
          status: 401,
        };
  }
}

export async function readPublisherProfile(accountId: AccountId): Promise<PublicProfileProjection> {
  return publicApiGet<PublicProfileProjection>(`/v1/publishers/${accountId}`);
}
