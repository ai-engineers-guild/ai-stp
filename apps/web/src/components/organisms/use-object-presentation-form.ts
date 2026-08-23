"use client";

import { useEffect, useRef, useState, useTransition } from "react";

import { updateObjectPresentationAction } from "@/actions/object-presentation";
import {
  isGithubRawUrl,
  isUploadedMediaUrl,
  isYoutubeVideoId,
  kindFromMime,
  validateComponentMediaFile,
} from "@/lib/component-media";
import type { OwnerPresentationMedia } from "@/lib/api/owner";

export type MediaUploadState = "idle" | "uploading" | "ready" | "error";

export type PresentationMediaDraft = OwnerPresentationMedia & {
  clientKey: string;
  localPreview: string | null;
  uploadState: MediaUploadState;
  pendingFile: File | null;
  itemError: string | null;
};

export type PresentationFormLabels = {
  saved: string;
  invalid: string;
  uploadFailed: string;
  unsupportedType: string;
  sizeExceeded: string;
  saveFailed: string;
  uploadInProgress: string;
  uploadRequired: string;
};

type UploadCtx = {
  stableId: string;
  labels: PresentationFormLabels;
  mediaRef: { current: PresentationMediaDraft[] };
  uploadGeneration: { current: Map<string, number> };
  patchMediaByKey: (clientKey: string, patch: Partial<PresentationMediaDraft>) => void;
  setError: (value: string | null) => void;
  setMessage: (value: string) => void;
};

function newClientKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `media_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

function emptyItem(): PresentationMediaDraft {
  return {
    clientKey: newClientKey(),
    kind: "image",
    url: "",
    alt: "",
    caption: "",
    localPreview: null,
    uploadState: "idle",
    pendingFile: null,
    itemError: null,
  };
}

function fromInitial(item: OwnerPresentationMedia): PresentationMediaDraft {
  const hasSource =
    item.kind === "youtube"
      ? isYoutubeVideoId(item.url)
      : isUploadedMediaUrl(item.url) || isGithubRawUrl(item.url);
  return {
    ...item,
    clientKey: newClientKey(),
    localPreview: null,
    uploadState: hasSource ? "ready" : "idle",
    pendingFile: null,
    itemError: null,
  };
}

function revokePreview(url: string | null | undefined) {
  if (url && url.startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
}

export function previewSrc(item: PresentationMediaDraft): string | null {
  if (item.localPreview) return item.localPreview;
  if (item.kind === "youtube" && isYoutubeVideoId(item.url)) {
    return `https://i.ytimg.com/vi/${item.url}/hqdefault.jpg`;
  }
  if (item.url && (isUploadedMediaUrl(item.url) || isGithubRawUrl(item.url))) {
    return item.url;
  }
  return null;
}

function mediaValid(item: PresentationMediaDraft): boolean {
  if (!item.alt.trim()) return false;
  if (item.kind === "youtube") return isYoutubeVideoId(item.url);
  return isUploadedMediaUrl(item.url) || isGithubRawUrl(item.url);
}

function itemBlocksSave(item: PresentationMediaDraft): boolean {
  return item.uploadState === "uploading" || item.uploadState === "error";
}

async function readUploadResponse(
  response: Response,
  fallback: string,
): Promise<{ public_url: string; kind?: "image" | "video" }> {
  const raw = await response.text();
  let body: { public_url?: string; kind?: "image" | "video"; message?: string } = {};
  if (raw) {
    try {
      body = JSON.parse(raw) as typeof body;
    } catch {
      throw new Error(fallback);
    }
  }
  if (!response.ok || !body.public_url) {
    throw new Error(body.message?.trim() || fallback);
  }
  if (!isUploadedMediaUrl(body.public_url)) {
    throw new Error(fallback);
  }
  if (body.kind === "image" || body.kind === "video") {
    return { public_url: body.public_url, kind: body.kind };
  }
  return { public_url: body.public_url };
}

function readLocalPreview(file: File): Promise<string | null> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      resolve(typeof reader.result === "string" ? reader.result : null);
    });
    reader.addEventListener("error", () => {
      resolve(null);
    });
    try {
      reader.readAsDataURL(file);
    } catch {
      resolve(null);
    }
  });
}

function mergeItem(
  item: PresentationMediaDraft,
  patch: Partial<PresentationMediaDraft>,
): PresentationMediaDraft {
  if ("localPreview" in patch && patch.localPreview !== item.localPreview && item.localPreview) {
    revokePreview(item.localPreview);
  }
  return { ...item, ...patch };
}

function validationMessage(
  items: PresentationMediaDraft[],
  labels: PresentationFormLabels,
): string {
  const firstError = items.find((item) => item.uploadState === "error");
  if (firstError) return firstError.itemError || labels.uploadRequired;
  if (items.some((item) => item.uploadState === "uploading")) {
    return labels.uploadInProgress;
  }
  const missingUpload = items.some(
    (item) =>
      item.kind !== "youtube" &&
      !isUploadedMediaUrl(item.url) &&
      !isGithubRawUrl(item.url) &&
      (item.localPreview || item.uploadState === "idle"),
  );
  return missingUpload ? labels.uploadRequired : labels.invalid;
}

async function runUpload(
  ctx: UploadCtx,
  clientKey: string,
  file: File,
  kind: "image" | "video",
): Promise<void> {
  const nextGen = (ctx.uploadGeneration.current.get(clientKey) ?? 0) + 1;
  ctx.uploadGeneration.current.set(clientKey, nextGen);
  const localPreview = await readLocalPreview(file);
  if (ctx.uploadGeneration.current.get(clientKey) !== nextGen) return;

  ctx.patchMediaByKey(clientKey, {
    kind,
    localPreview,
    uploadState: "uploading",
    url: "",
    pendingFile: file,
    itemError: null,
  });
  ctx.setError(null);
  ctx.setMessage("");

  try {
    const response = await fetch(
      `/api/objects/component/${encodeURIComponent(ctx.stableId)}/media`,
      {
        method: "POST",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      },
    );
    const body = await readUploadResponse(response, ctx.labels.uploadFailed);
    if (ctx.uploadGeneration.current.get(clientKey) !== nextGen) return;
    if (!ctx.mediaRef.current.some((item) => item.clientKey === clientKey)) return;
    ctx.patchMediaByKey(clientKey, {
      kind: body.kind ?? kind,
      url: body.public_url,
      uploadState: "ready",
      pendingFile: null,
      itemError: null,
    });
    ctx.setError(null);
  } catch (err) {
    if (ctx.uploadGeneration.current.get(clientKey) !== nextGen) return;
    if (!ctx.mediaRef.current.some((item) => item.clientKey === clientKey)) return;
    const detail = err instanceof Error ? err.message : ctx.labels.uploadFailed;
    ctx.patchMediaByKey(clientKey, {
      uploadState: "error",
      url: "",
      pendingFile: file,
      itemError: detail,
    });
    ctx.setError(detail);
  }
}

export function useObjectPresentationForm(input: {
  locale: string;
  stableId: string;
  csrfToken: string;
  initialBio: string;
  initialMedia: OwnerPresentationMedia[];
  labels: PresentationFormLabels;
}) {
  const { locale, stableId, csrfToken, initialBio, initialMedia, labels } = input;
  const [bio, setBio] = useState(initialBio);
  const [media, setMedia] = useState<PresentationMediaDraft[]>(() =>
    initialMedia.length > 0 ? initialMedia.map(fromInitial) : [emptyItem()],
  );
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, startSaveTransition] = useTransition();
  // Assigned after commit, not during render: the unmount cleanup below reads
  // it to revoke object URLs, and a discarded render must not decide which
  // ones those are.
  const mediaRef = useRef(media);
  useEffect(() => {
    mediaRef.current = media;
  }, [media]);
  const uploadGeneration = useRef(new Map<string, number>());

  useEffect(() => {
    return () => {
      for (const item of mediaRef.current) revokePreview(item.localPreview);
    };
  }, []);

  function patchMediaByKey(clientKey: string, patch: Partial<PresentationMediaDraft>) {
    setMedia((items) =>
      items.map((item) => (item.clientKey === clientKey ? mergeItem(item, patch) : item)),
    );
  }

  function patchMedia(index: number, patch: Partial<PresentationMediaDraft>) {
    setMedia((items) =>
      items.map((item, itemIndex) => (itemIndex === index ? mergeItem(item, patch) : item)),
    );
  }

  const uploadCtx: UploadCtx = {
    stableId,
    labels,
    mediaRef,
    uploadGeneration,
    patchMediaByKey,
    setError,
    setMessage,
  };

  function onFile(index: number, file: File | null) {
    if (!file) return;
    const item = mediaRef.current[index];
    if (!item) return;
    const reason = validateComponentMediaFile(file);
    if (reason === "unsupported" || reason === "size") {
      const messageText = reason === "size" ? labels.sizeExceeded : labels.unsupportedType;
      setError(messageText);
      patchMediaByKey(item.clientKey, {
        uploadState: "error",
        itemError: messageText,
        pendingFile: null,
      });
      return;
    }
    const kind = kindFromMime(file.type);
    if (!kind) {
      setError(labels.unsupportedType);
      patchMediaByKey(item.clientKey, {
        uploadState: "error",
        itemError: labels.unsupportedType,
        pendingFile: null,
      });
      return;
    }
    void runUpload(uploadCtx, item.clientKey, file, kind);
  }

  function retryUpload(index: number) {
    const item = mediaRef.current[index];
    if (!item?.pendingFile) return;
    const kind = kindFromMime(item.pendingFile.type);
    if (!kind) {
      setError(labels.unsupportedType);
      return;
    }
    void runUpload(uploadCtx, item.clientKey, item.pendingFile, kind);
  }

  function save() {
    setError(null);
    setMessage("");
    const items = mediaRef.current;
    if (items.some(itemBlocksSave) || !items.every(mediaValid)) {
      setError(validationMessage(items, labels));
      return;
    }
    startSaveTransition(async () => {
      const payload = mediaRef.current.map(({ kind, url, alt, caption }) => ({
        kind,
        url,
        alt: alt.trim(),
        caption: caption.trim(),
      }));
      const result = await updateObjectPresentationAction({
        csrfToken,
        stableId,
        locale,
        bio,
        media: payload,
      });
      if (result.ok) {
        setMessage(labels.saved);
        setMedia((current) =>
          current.map((item) => ({
            ...item,
            uploadState: "ready" as const,
            pendingFile: null,
            itemError: null,
          })),
        );
      } else {
        setError(result.message || labels.saveFailed);
      }
    });
  }

  const uploading = media.some((item) => item.uploadState === "uploading");
  const hasBlockingUpload = media.some(itemBlocksSave);
  const canSave = !saving && !uploading && !hasBlockingUpload && media.every(mediaValid);

  return {
    bio,
    setBio,
    media,
    saving,
    uploading,
    pending: saving || uploading,
    canSave,
    message,
    error,
    previewSrc,
    patchMedia,
    addMedia: () => {
      setMedia((items) => (items.length >= 5 ? items : [...items, emptyItem()]));
    },
    removeMedia: (index: number) => {
      setMedia((items) => {
        const target = items[index];
        if (target) {
          revokePreview(target.localPreview);
          uploadGeneration.current.delete(target.clientKey);
        }
        return items.filter((_, itemIndex) => itemIndex !== index);
      });
    },
    onFile,
    retryUpload,
    save,
    canAdd: media.length < 5,
  };
}
