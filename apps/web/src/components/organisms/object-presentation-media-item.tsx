"use client";

/* eslint-disable max-lines */

import { useId, useRef, useState } from "react";

import { Button } from "@/components/atoms/button";
import type { PresentationMediaDraft } from "@/components/organisms/use-object-presentation-form";
import {
  COMPONENT_MEDIA_ACCEPT,
  isExternalMediaUrl,
  isUploadedMediaUrl,
  kindFromMediaUrl,
  normalizeGithubUrl,
  normalizeYoutubeUrl,
} from "@/lib/component-media";
import { Icon } from "@/theme/icons";

export type MediaItemLabels = {
  remove: string;
  kind: string;
  alt: string;
  caption: string;
  upload: string;
  uploading: string;
  youtubeHint: string;
  githubHint: string;
  youtubePlaceholder: string;
  githubPlaceholder: string;
  preview: string;
  retryUpload: string;
  replaceUpload: string;
  sourceUpload: string;
  sourceGithub: string;
  sourceYoutube: string;
  sourceChoice: string;
  sourceUrl?: string;
  urlHint?: string;
  urlPlaceholder?: string;
  uploadedReady: string;
  itemStatusIdle: string;
  itemStatusUploading: string;
  itemStatusReady: string;
  itemStatusError: string;
  altRequired: string;
  invalid: string;
  kindImage: string;
  kindVideo: string;
};

type SourceMode = "upload" | "url";

function statusLabel(
  state: PresentationMediaDraft["uploadState"],
  labels: MediaItemLabels,
): string {
  if (state === "uploading") return labels.itemStatusUploading;
  if (state === "ready") return labels.itemStatusReady;
  if (state === "error") return labels.itemStatusError;
  return labels.itemStatusIdle;
}

function resolveSourceMode(item: PresentationMediaDraft): SourceMode {
  return item.sourceMode;
}

function applySourceMode(
  item: PresentationMediaDraft,
  mode: SourceMode,
): Partial<PresentationMediaDraft> {
  if (mode === "url") {
    return {
      sourceMode: "url",
      kind: item.kind,
      url: item.kind === "youtube" || isExternalMediaUrl(item.url) ? item.url : "",
      uploadState: "idle",
      localPreview: null,
      pendingFile: null,
      itemError: null,
    };
  }
  return {
    sourceMode: "upload",
    kind: item.kind === "video" ? "video" : "image",
    url: isUploadedMediaUrl(item.url) ? item.url : "",
    uploadState: isUploadedMediaUrl(item.url) ? "ready" : "idle",
    itemError: null,
  };
}

function MediaPreview(props: {
  item: PresentationMediaDraft;
  previewSrc: string | null;
  labels: MediaItemLabels;
  uploading: boolean;
  onPatch: (patch: Partial<PresentationMediaDraft>) => void;
}) {
  const { item, previewSrc, labels, uploading, onPatch } = props;
  const [mode, setMode] = useState<"image" | "video" | "error">(
    item.kind === "video" ? "video" : "image",
  );

  const youtubeId = item.kind === "youtube" ? normalizeYoutubeUrl(item.url) : null;
  if (youtubeId) {
    return (
      <iframe
        src={`https://www.youtube-nocookie.com/embed/${youtubeId}?rel=0`}
        title={item.alt || labels.preview}
        className="h-full w-full border-0"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowFullScreen
      />
    );
  }

  if (previewSrc) {
    if (mode === "video") {
      return (
        <video
          src={previewSrc}
          playsInline
          controls
          preload="metadata"
          aria-label={item.alt || labels.preview}
          crossOrigin="anonymous"
          onError={() => {
            setMode("error");
            onPatch({ uploadState: "error", itemError: labels.invalid });
          }}
          onLoadedMetadata={() => {
            onPatch({ kind: "video", uploadState: "ready", itemError: null });
          }}
        >
          <track
            kind="captions"
            srcLang="en"
            label={labels.preview}
            src="data:text/vtt,WEBVTT%0A%0A"
          />
        </video>
      );
    }
    if (mode === "image") {
      return (
        <img
          src={previewSrc}
          alt={item.alt || ""}
          className="h-full w-full object-cover"
          onLoad={() => {
            onPatch({ kind: "image", uploadState: "ready", itemError: null });
          }}
          onError={() => {
            if (item.kind !== "video") {
              setMode("video");
              onPatch({ kind: "video", uploadState: "idle", itemError: null });
            } else {
              setMode("error");
              onPatch({ uploadState: "error", itemError: labels.invalid });
            }
          }}
        />
      );
    }
  }
  return (
    <div className="text-muted-foreground flex flex-col items-center gap-2 p-4 text-center text-xs">
      <Icon
        name={uploading ? "loader" : "camera"}
        size="md"
        className={uploading ? "animate-spin" : ""}
      />
      <span>{uploading ? labels.uploading : labels.preview}</span>
    </div>
  );
}

function UploadActions(props: {
  baseId: string;
  statusId: string;
  labels: MediaItemLabels;
  uploading: boolean;
  uploadedReady: boolean;
  hasPreview: boolean;
  canRetry: boolean;
  disabled: boolean;
  onFile: (file: File | null) => void;
  onRetry: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadLabel = props.uploading
    ? props.labels.uploading
    : props.uploadedReady || props.hasPreview
      ? props.labels.replaceUpload
      : props.labels.upload;

  return (
    <div className="flex flex-wrap gap-2">
      <input
        ref={inputRef}
        id={`${props.baseId}-file`}
        type="file"
        accept={COMPONENT_MEDIA_ACCEPT}
        className="sr-only"
        onChange={(event) => {
          props.onFile(event.target.files?.[0] ?? null);
          event.target.value = "";
        }}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="min-h-11"
        disabled={props.disabled}
        aria-describedby={props.statusId}
        onClick={() => {
          inputRef.current?.click();
        }}
      >
        <Icon
          name={props.uploading ? "loader" : "camera"}
          size="sm"
          className={props.uploading ? "animate-spin" : ""}
        />
        {uploadLabel}
      </Button>
      {props.canRetry ? (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="min-h-11"
          disabled={props.disabled}
          onClick={props.onRetry}
        >
          <Icon name="alert" size="sm" />
          {props.labels.retryUpload}
        </Button>
      ) : null}
    </div>
  );
}

function MediaMetadataFields(props: {
  item: PresentationMediaDraft;
  labels: MediaItemLabels;
  fieldClass: string;
  sourceMode: SourceMode;
  controlsDisabled: boolean;
  sourceModeId: string;
  urlId: string;
  altId: string;
  onPatch: (patch: Partial<PresentationMediaDraft>) => void;
  onRemove: () => void;
  busy: boolean;
  urlError?: string | undefined;
  altError?: string | undefined;
  itemError?: string | undefined;
}) {
  const {
    item,
    labels,
    fieldClass,
    sourceMode,
    controlsDisabled,
    onPatch,
    onRemove,
    busy,
    urlError,
    altError,
    itemError,
  } = props;

  return (
    <div className="grid gap-3">
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">{labels.sourceChoice}</legend>
        <div id={props.sourceModeId} className="flex flex-wrap gap-2">
          {(["upload", "url"] as const).map((mode) => (
            <Button
              key={mode}
              type="button"
              variant={sourceMode === mode ? "secondary" : "outline"}
              className="min-h-11"
              aria-pressed={sourceMode === mode}
              disabled={controlsDisabled}
              onClick={() => {
                onPatch(applySourceMode(item, mode));
              }}
            >
              <Icon name={mode === "upload" ? "camera" : "link"} size="sm" />
              {mode === "upload" ? labels.sourceUpload : (labels.sourceUrl ?? labels.sourceGithub)}
            </Button>
          ))}
        </div>
      </fieldset>

      {sourceMode === "url" ? (
        <div className="space-y-1">
          <label htmlFor={props.urlId} className="text-sm font-medium">
            {labels.sourceUrl ?? labels.sourceGithub}
            <span className="text-destructive"> *</span>
          </label>
          <input
            id={props.urlId}
            className={`${fieldClass} ${urlError || itemError ? "border-destructive focus-visible:ring-destructive" : ""}`}
            required
            maxLength={2048}
            value={item.url}
            aria-invalid={Boolean(urlError || itemError)}
            aria-describedby={urlError || itemError ? `${props.urlId}-error` : undefined}
            placeholder={labels.urlPlaceholder ?? "https://…"}
            disabled={controlsDisabled}
            onChange={(event) => {
              const value = event.target.value;
              const youtube = normalizeYoutubeUrl(value);
              const normalized = normalizeGithubUrl(value);
              onPatch({
                kind: kindFromMediaUrl(normalized) ?? "image",
                url: youtube ?? normalized,
                uploadState: "idle",
                localPreview: null,
                pendingFile: null,
                itemError:
                  value && !youtube && !isExternalMediaUrl(normalized) ? labels.invalid : null,
                ...(youtube ? { uploadState: "ready" as const } : {}),
              });
            }}
          />
          <p className="text-muted-foreground text-xs">{labels.urlHint ?? labels.githubHint}</p>
          {urlError || itemError ? (
            <p id={`${props.urlId}-error`} className="text-destructive text-xs" role="alert">
              {urlError ?? itemError}
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-1">
        <label htmlFor={props.altId} className="text-sm font-medium">
          {labels.alt}
        </label>
        <input
          id={props.altId}
          className={`${fieldClass} ${altError ? "border-destructive focus-visible:ring-destructive" : ""}`}
          maxLength={240}
          value={item.alt}
          aria-invalid={Boolean(altError)}
          aria-describedby={altError ? `${props.altId}-error` : undefined}
          onChange={(event) => {
            onPatch({ alt: event.target.value });
          }}
        />
        <p className="text-muted-foreground text-xs">{labels.altRequired}</p>
        {altError ? (
          <p id={`${props.altId}-error`} className="text-destructive text-xs" role="alert">
            {altError}
          </p>
        ) : null}
      </div>

      <div className="pt-1">
        <Button
          type="button"
          variant="ghost"
          className="min-h-11 justify-self-start"
          disabled={busy}
          onClick={onRemove}
        >
          {labels.remove}
        </Button>
      </div>
    </div>
  );
}

export function MediaItemEditor(props: {
  index: number;
  item: PresentationMediaDraft;
  labels: MediaItemLabels;
  fieldClass: string;
  previewSrc: string | null;
  busy: boolean;
  onPatch: (patch: Partial<PresentationMediaDraft>) => void;
  onFile: (file: File | null) => void;
  onRetry: () => void;
  onRemove: () => void;
  errors?:
    | {
        url?: string | undefined;
        alt?: string | undefined;
        item?: string | undefined;
      }
    | undefined;
}) {
  const {
    index,
    item,
    labels,
    fieldClass,
    previewSrc,
    busy,
    onPatch,
    onFile,
    onRetry,
    onRemove,
    errors,
  } = props;
  const baseId = useId();
  const sourceMode = resolveSourceMode(item);
  const isYoutube = item.kind === "youtube";
  const uploading = item.uploadState === "uploading";
  const uploadedReady =
    sourceMode === "upload" && isUploadedMediaUrl(item.url) && item.uploadState === "ready";
  const controlsDisabled = busy || uploading;
  const statusTone =
    item.uploadState === "error"
      ? "text-destructive text-xs"
      : item.uploadState === "ready"
        ? "text-foreground text-xs"
        : "text-muted-foreground text-xs";

  return (
    <article
      className={`${errors?.url || errors?.alt || errors?.item ? "border-destructive" : "border-border"} bg-card grid gap-4 rounded-lg border p-4 md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] md:gap-5`}
      aria-labelledby={`${baseId}-status`}
    >
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            {index + 1} / 5
          </p>
          <p id={`${baseId}-status`} className={statusTone} aria-live="polite">
            {statusLabel(item.uploadState, labels)}
          </p>
        </div>
        <div
          className="bg-muted relative flex aspect-video w-full items-center justify-center overflow-hidden rounded-md"
          aria-label={labels.preview}
        >
          <MediaPreview
            key={`${item.kind}:${previewSrc ?? ""}`}
            item={item}
            previewSrc={previewSrc}
            labels={labels}
            uploading={uploading}
            onPatch={onPatch}
          />
        </div>
        {sourceMode === "upload" && !isYoutube ? (
          <UploadActions
            baseId={baseId}
            statusId={`${baseId}-status`}
            labels={labels}
            uploading={uploading}
            uploadedReady={uploadedReady}
            hasPreview={Boolean(item.localPreview)}
            canRetry={item.uploadState === "error" && Boolean(item.pendingFile)}
            disabled={controlsDisabled}
            onFile={onFile}
            onRetry={onRetry}
          />
        ) : null}
        {item.itemError ? (
          <p className="text-destructive text-xs" role="alert">
            {item.itemError}
          </p>
        ) : null}
        {uploadedReady ? (
          <p className="text-muted-foreground text-xs">{labels.uploadedReady}</p>
        ) : null}
      </div>

      <MediaMetadataFields
        item={item}
        labels={labels}
        fieldClass={fieldClass}
        sourceMode={sourceMode}
        controlsDisabled={controlsDisabled}
        sourceModeId={`${baseId}-source-mode`}
        urlId={`${baseId}-url`}
        altId={`${baseId}-alt`}
        onPatch={onPatch}
        onRemove={onRemove}
        busy={busy}
        urlError={errors?.url}
        altError={errors?.alt}
        itemError={errors?.item}
      />
    </article>
  );
}
