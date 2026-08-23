"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import { useTranslations } from "next-intl";

import { ApiError } from "@/lib/api/errors";
import type { OwnerPublicProfile, ProfileLink } from "@/lib/api/public-profile";
import {
  importAvatarFromIdentity,
  publishOwnerPublicProfile,
  saveOwnerPublicProfileDraft,
} from "@/lib/api/public-profile";
import {
  PROFILE_PREVIEW_STORAGE_KEY,
  readLocalProfilePreview,
  type LocalProfilePreview,
} from "@/lib/profile-preview-storage";

export const PROFILE_BIO_MAX = 1500;

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.message) {
    return `${fallback}: ${error.message}`;
  }
  return fallback;
}

async function avatarUploadResult(response: Response) {
  const body = (await response.json()) as {
    avatar_asset_id?: string;
    public_url?: string | null;
    message?: string;
  };
  if (!response.ok || !body.avatar_asset_id) {
    throw new Error(body.message || "avatar upload failed");
  }
  return { avatar_asset_id: body.avatar_asset_id, public_url: body.public_url ?? null };
}

/** State + mutations for the public profile editor. */
// The hook owns one cohesive form state machine; splitting mutations would obscure its transitions.
// eslint-disable-next-line max-lines-per-function
export function useProfileForm(initial: OwnerPublicProfile, sessionToken: string) {
  const t = useTranslations("account");
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState(initial.state);
  const [baseRevisionId, setBaseRevisionId] = useState(initial.editable.base_revision_id);
  const [digest, setDigest] = useState(initial.editable.base_content_digest);
  const [displayName, setDisplayName] = useState(initial.editable.fields.display_name ?? "");
  const [bio, setBio] = useState(initial.editable.fields.bio ?? "");
  const [bioMode, setBioMode] = useState<"plain" | "render">("plain");
  const [links, setLinks] = useState<ProfileLink[]>([...initial.editable.fields.links]);
  const [avatarAssetId, setAvatarAssetId] = useState<string | null>(
    initial.editable.fields.avatar_asset_id,
  );
  const [avatarUrl, setAvatarUrl] = useState<string | null>(initial.editable.avatar_url);
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [storageReady, setStorageReady] = useState(false);

  const shownAvatar = localPreview ?? avatarUrl;
  const bioError =
    bio.length > PROFILE_BIO_MAX
      ? t("profileErrorBio")
      : /<[^>\s]+[^>]*>|javascript:|data:/i.test(bio)
        ? t("profileErrorBioMd")
        : null;

  useEffect(() => {
    return () => {
      if (localPreview) URL.revokeObjectURL(localPreview);
    };
  }, [localPreview]);

  // The one effect here that stays an effect, and the reason is the difference
  // between deriving state and seeding it. Everywhere else in this change the
  // value was read-only — a resolved theme, a browser capability, a saved
  // consent — so it could be read during render and never stored. This draft
  // is the *initial value of fields the user then types over*: it has to be
  // written into state, and it cannot be written before the browser exists.
  //
  // `useState` cannot take it either, because a lazy initialiser runs on the
  // server too, where `sessionStorage` does not exist and where producing
  // different markup would break hydration.
  //
  useEffect(() => {
    const restored = readLocalProfilePreview(
      initial.account_id,
      initial.editable.base_revision_id,
      initial.editable.base_content_digest,
    );
    /* eslint-disable react-hooks/set-state-in-effect -- seeds editable state
       from browser storage after hydration; the reasoning is above. */
    if (restored) {
      setDisplayName(restored.displayName);
      setBio(restored.bio);
      setLinks(restored.links);
      setAvatarAssetId(restored.avatarAssetId);
      setAvatarUrl(restored.avatarUrl);
    }
    setStorageReady(true);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [initial.account_id, initial.editable.base_revision_id, initial.editable.base_content_digest]);

  const persistPreview = useCallback(() => {
    const preview: LocalProfilePreview = {
      accountId: initial.account_id,
      baseRevisionId,
      baseContentDigest: digest,
      displayName,
      bio,
      links,
      avatarAssetId,
      avatarUrl: shownAvatar,
    };
    window.sessionStorage.setItem(PROFILE_PREVIEW_STORAGE_KEY, JSON.stringify(preview));
  }, [
    initial.account_id,
    baseRevisionId,
    digest,
    displayName,
    bio,
    links,
    avatarAssetId,
    shownAvatar,
  ]);

  useEffect(() => {
    if (!storageReady) return;
    persistPreview();
  }, [storageReady, persistPreview]);

  function payload(nextAvatar: string | null = avatarAssetId) {
    return {
      display_name: displayName.trim() || null,
      bio: bio || null,
      links,
      avatar_asset_id: nextAvatar,
    };
  }

  function clearLocalPreview() {
    setLocalPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }

  function applyAvatar(result: { avatar_asset_id: string; public_url: string | null }) {
    setAvatarAssetId(result.avatar_asset_id);
    if (result.public_url) setAvatarUrl(result.public_url);
    setMessage(t("profileAvatarReady"));
  }

  function saveDraft() {
    setError(null);
    setMessage(null);
    startTransition(async () => {
      try {
        const saved = await saveOwnerPublicProfileDraft(sessionToken, payload(), digest);
        setBaseRevisionId(saved.editable.base_revision_id);
        setDigest(saved.draft.content_digest);
        setStatus(saved.state);
        setAvatarUrl(saved.draft.avatar_url);
        window.sessionStorage.removeItem(PROFILE_PREVIEW_STORAGE_KEY);
        setMessage(t("profileDraftSaved"));
      } catch (err) {
        setError(errorMessage(err, t("profileSaveFailed")));
      }
    });
  }

  function publish() {
    setError(null);
    setMessage(null);
    startTransition(async () => {
      try {
        const saved = await saveOwnerPublicProfileDraft(sessionToken, payload(), null);
        const nextDigest = saved.draft.content_digest;
        if (!nextDigest) {
          setError(t("profilePublishNeedDraft"));
          return;
        }
        await publishOwnerPublicProfile(sessionToken, nextDigest);
        setBaseRevisionId(saved.draft.revision_id);
        setDigest(nextDigest);
        setStatus("published");
        window.sessionStorage.removeItem(PROFILE_PREVIEW_STORAGE_KEY);
        setMessage(t("profilePublished"));
      } catch (err) {
        setError(errorMessage(err, t("profilePublishFailed")));
      }
    });
  }

  function onFile(file: File | null) {
    if (!file) return;
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      if (typeof reader.result === "string") setLocalPreview(reader.result);
    });
    reader.readAsDataURL(file);
    setError(null);
    setMessage(null);
    startTransition(async () => {
      try {
        const response = await fetch("/api/account/avatar", {
          method: "POST",
          headers: { "Content-Type": file.type || "image/png" },
          body: file,
        });
        applyAvatar(await avatarUploadResult(response));
      } catch (err) {
        setError(errorMessage(err, t("profileAvatarFailed")));
      }
    });
  }

  function onImport(provider: "github" | "google") {
    setError(null);
    setMessage(null);
    startTransition(async () => {
      try {
        applyAvatar(await importAvatarFromIdentity(sessionToken, provider));
      } catch (err) {
        setError(errorMessage(err, t("profileAvatarFailed")));
      }
    });
  }

  function onRemoveAvatar() {
    setAvatarAssetId(null);
    setAvatarUrl(null);
    clearLocalPreview();
  }

  function restorePublished() {
    if (!initial.published) return;
    setDisplayName(initial.published.fields.display_name ?? "");
    setBio(initial.published.fields.bio ?? "");
    setLinks([...initial.published.fields.links]);
    setAvatarAssetId(initial.published.fields.avatar_asset_id);
    setAvatarUrl(initial.published.avatar_url);
    clearLocalPreview();
    setError(null);
    setMessage(t("profilePublishedRestored"));
  }

  return {
    t,
    pending,
    error,
    message,
    status,
    digest,
    displayName,
    setDisplayName,
    bio,
    setBio,
    bioMode,
    setBioMode,
    bioError,
    links,
    setLinks,
    shownAvatar,
    saveDraft,
    publish,
    onFile,
    onImport,
    onRemoveAvatar,
    restorePublished,
    persistPreview,
    canRestorePublished: Boolean(initial.published),
  };
}
