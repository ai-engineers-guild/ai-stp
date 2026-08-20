"use client";

import { useId, useRef } from "react";

import { Button } from "@/components/atoms/button";
import type { PresentationMediaDraft } from "@/components/organisms/use-object-presentation-form";
import { COMPONENT_MEDIA_ACCEPT, isUploadedMediaUrl } from "@/lib/component-media";
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
  preview: string;
  retryUpload: string;
  replaceUpload: string;
  sourceUpload: string;
  sourceGithub: string;
  sourceYoutube: string;
  sourceChoice: string;
  uploadedReady: string;
  itemStatusIdle: string;
  itemStatusUploading: string;
  itemStatusReady: string;
  itemStatusError: string;
  altRequired: string;
  kindImage: string;
  kindVideo: string;
};

type SourceMode = "upload" | "github" | "youtube";

function statusLabel(
  state: PresentationMediaDraft["uploadState"],
  labels: MediaItemLabels,
): string {
  if (state === "uploading") return labels.itemStatusUploading;
  if (state === "ready") return labels.itemStatusReady;
  if (state === "error") return labels.itemStatusError;
  return labels.itemStatusIdle;
}

function isGithubRawUrlSafe(url: string): boolean {
  return url.startsWith("https://raw.githubusercontent.com/");
}

function isYoutubeVideoIdSafe(url: string): boolean {
  return /^[A-Za-z0-9_-]{11}$/.test(url);
}

function resolveSourceMode(item: PresentationMediaDraft): SourceMode {
  if (item.kind === "youtube") return "youtube";
  if (isGithubRawUrlSafe(item.url)) return "github";
  return "upload";
}

function applySourceMode(
  item: PresentationMediaDraft,
  mode: SourceMode,
): Partial<PresentationMediaDraft> {
  if (mode === "youtube") {
    return {
      kind: "youtube",
      url: isYoutubeVideoIdSafe(item.url) ? item.url : "",
      localPreview: null,
      uploadState: "idle",
      pendingFile: null,
      itemError: null,
    };
  }
  if (mode === "github") {
    return {
      kind: item.kind === "video" ? "video" : "image",
      url: isGithubRawUrlSafe(item.url) ? item.url : "",
      localPreview: null,
      uploadState: "idle",
      pendingFile: null,
      itemError: null,
    };
  }
  return {
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
}) {
  const { item, previewSrc, labels, uploading } = props;
  if (previewSrc) {
    if (item.kind === "video" && !previewSrc.includes("ytimg")) {
      return (
        <video
          src={previewSrc}
          muted
          playsInline
          loop
          autoPlay
          className="h-full w-full object-cover"
        />
      );
    }
    return <img src={previewSrc} alt={item.alt || ""} className="h-full w-full object-cover" />;
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
  isYoutube: boolean;
  showGithubField: boolean;
  uploadedReady: boolean;
  controlsDisabled: boolean;
  kindId: string;
  sourceModeId: string;
  urlId: string;
  altId: string;
  captionId: string;
  onPatch: (patch: Partial<PresentationMediaDraft>) => void;
  onRemove: () => void;
  busy: boolean;
}) {
  const {
    item,
    labels,
    fieldClass,
    sourceMode,
    isYoutube,
    showGithubField,
    uploadedReady,
    controlsDisabled,
    onPatch,
    onRemove,
    busy,
  } = props;

  return (
    <div className="grid gap-3">
      <div className="space-y-1">
        <label htmlFor={props.sourceModeId} className="text-sm font-medium">
          {labels.sourceChoice}
        </label>
        <select
          id={props.sourceModeId}
          className={fieldClass}
          value={sourceMode}
          disabled={controlsDisabled}
          onChange={(event) => {
            onPatch(applySourceMode(item, event.target.value as SourceMode));
          }}
        >
          <option value="upload">{labels.sourceUpload}</option>
          <option value="github">{labels.sourceGithub}</option>
          <option value="youtube">{labels.sourceYoutube}</option>
        </select>
      </div>

      {!isYoutube ? (
        <div className="space-y-1">
          <label htmlFor={props.kindId} className="text-sm font-medium">
            {labels.kind}
          </label>
          <select
            id={props.kindId}
            className={fieldClass}
            value={item.kind === "video" ? "video" : "image"}
            disabled={controlsDisabled || uploadedReady}
            onChange={(event) => {
              onPatch({ kind: event.target.value as "image" | "video" });
            }}
          >
            <option value="image">{labels.kindImage}</option>
            <option value="video">{labels.kindVideo}</option>
          </select>
        </div>
      ) : null}

      {isYoutube || showGithubField ? (
        <div className="space-y-1">
          <label htmlFor={props.urlId} className="text-sm font-medium">
            {isYoutube ? labels.sourceYoutube : labels.sourceGithub}
            <span className="text-destructive"> *</span>
          </label>
          <input
            id={props.urlId}
            className={fieldClass}
            required
            maxLength={2048}
            value={item.url}
            placeholder={isYoutube ? "dQw4w9WgXcQ" : "https://raw.githubusercontent.com/..."}
            disabled={controlsDisabled}
            onChange={(event) => {
              onPatch({
                url: event.target.value,
                uploadState: "idle",
                localPreview: null,
                pendingFile: null,
                itemError: null,
              });
            }}
          />
          <p className="text-muted-foreground text-xs">
            {isYoutube ? labels.youtubeHint : labels.githubHint}
          </p>
        </div>
      ) : null}

      <div className="space-y-1">
        <label htmlFor={props.altId} className="text-sm font-medium">
          {labels.alt}
          <span className="text-destructive"> *</span>
        </label>
        <input
          id={props.altId}
          className={fieldClass}
          required
          maxLength={240}
          value={item.alt}
          aria-required="true"
          onChange={(event) => {
            onPatch({ alt: event.target.value });
          }}
        />
        <p className="text-muted-foreground text-xs">{labels.altRequired}</p>
      </div>

      <div className="space-y-1">
        <label htmlFor={props.captionId} className="text-sm font-medium">
          {labels.caption}
        </label>
        <input
          id={props.captionId}
          className={fieldClass}
          maxLength={500}
          value={item.caption}
          onChange={(event) => {
            onPatch({ caption: event.target.value });
          }}
        />
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
}) {
  const { index, item, labels, fieldClass, previewSrc, busy, onPatch, onFile, onRetry, onRemove } =
    props;
  const baseId = useId();
  const sourceMode = resolveSourceMode(item);
  const isYoutube = sourceMode === "youtube";
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
      className="border-border bg-card grid gap-4 rounded-lg border p-4 md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] md:gap-5"
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
          <MediaPreview item={item} previewSrc={previewSrc} labels={labels} uploading={uploading} />
        </div>
        {!isYoutube ? (
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
        isYoutube={isYoutube}
        showGithubField={sourceMode === "github"}
        uploadedReady={uploadedReady}
        controlsDisabled={controlsDisabled}
        kindId={`${baseId}-kind`}
        sourceModeId={`${baseId}-source-mode`}
        urlId={`${baseId}-url`}
        altId={`${baseId}-alt`}
        captionId={`${baseId}-caption`}
        onPatch={onPatch}
        onRemove={onRemove}
        busy={busy}
      />
    </article>
  );
}
