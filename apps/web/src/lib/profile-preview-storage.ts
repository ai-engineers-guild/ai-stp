import type { ProfileLink } from "@/lib/api/public-profile";

export const PROFILE_PREVIEW_STORAGE_KEY = "ai-stp:profile-preview:v2";

export type LocalProfilePreview = {
  accountId: string;
  baseRevisionId: string | null;
  baseContentDigest: string | null;
  displayName: string;
  bio: string;
  links: ProfileLink[];
  avatarAssetId: string | null;
  avatarUrl: string | null;
};

export function readLocalProfilePreview(
  accountId: string,
  baseRevisionId?: string | null,
  baseContentDigest?: string | null,
): LocalProfilePreview | null {
  try {
    const raw = window.sessionStorage.getItem(PROFILE_PREVIEW_STORAGE_KEY);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (!isLocalProfilePreview(value) || value.accountId !== accountId) return null;
    if (
      baseRevisionId !== undefined &&
      (value.baseRevisionId !== baseRevisionId || value.baseContentDigest !== baseContentDigest)
    ) {
      window.sessionStorage.removeItem(PROFILE_PREVIEW_STORAGE_KEY);
      return null;
    }
    return value;
  } catch {
    return null;
  }
}

function isLocalProfilePreview(value: unknown): value is LocalProfilePreview {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.accountId === "string" &&
    (candidate.baseRevisionId === null || typeof candidate.baseRevisionId === "string") &&
    (candidate.baseContentDigest === null || typeof candidate.baseContentDigest === "string") &&
    typeof candidate.displayName === "string" &&
    typeof candidate.bio === "string" &&
    (candidate.avatarAssetId === null || typeof candidate.avatarAssetId === "string") &&
    (candidate.avatarUrl === null || typeof candidate.avatarUrl === "string") &&
    Array.isArray(candidate.links) &&
    candidate.links.every(isProfileLink)
  );
}

function isProfileLink(value: unknown): value is ProfileLink {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.label === "string" && typeof candidate.url === "string";
}
