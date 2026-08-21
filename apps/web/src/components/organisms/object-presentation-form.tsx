"use client";

import { Button } from "@/components/atoms/button";
import { MediaItemEditor } from "@/components/organisms/object-presentation-media-item";
import { useObjectPresentationForm } from "@/components/organisms/use-object-presentation-form";
import type { OwnerPresentationMedia } from "@/lib/api/owner";

type Labels = {
  bio: string;
  media: string;
  addMedia: string;
  remove: string;
  kind: string;
  url: string;
  alt: string;
  caption: string;
  save: string;
  saving: string;
  saved: string;
  help: string;
  upload: string;
  uploading: string;
  requirements: string;
  youtubeHint: string;
  githubHint: string;
  youtubePlaceholder: string;
  githubPlaceholder: string;
  invalid: string;
  uploadFailed: string;
  unsupportedType: string;
  sizeExceeded: string;
  saveFailed: string;
  preview: string;
  uploadInProgress: string;
  uploadRequired: string;
  retryUpload: string;
  replaceUpload: string;
  sourceUpload: string;
  sourceGithub: string;
  sourceYoutube: string;
  sourceChoice: string;
  uploadedReady: string;
  uploadError: string;
  itemStatusIdle: string;
  itemStatusUploading: string;
  itemStatusReady: string;
  itemStatusError: string;
  altRequired: string;
  mediaCount: string;
  kindImage: string;
  kindVideo: string;
  kindYoutube: string;
};

const FIELD_CLASS =
  "border-input bg-background focus-visible:ring-ring min-h-11 w-full rounded-sm border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60";

export function ObjectPresentationForm({
  locale,
  stableId,
  csrfToken,
  initialBio,
  initialMedia,
  labels,
}: {
  locale: string;
  stableId: string;
  csrfToken: string;
  initialBio: string;
  initialMedia: OwnerPresentationMedia[];
  labels: Labels;
}) {
  const form = useObjectPresentationForm({
    locale,
    stableId,
    csrfToken,
    initialBio,
    initialMedia,
    labels: {
      saved: labels.saved,
      invalid: labels.invalid,
      uploadFailed: labels.uploadFailed,
      unsupportedType: labels.unsupportedType,
      sizeExceeded: labels.sizeExceeded,
      saveFailed: labels.saveFailed,
      uploadInProgress: labels.uploadInProgress,
      uploadRequired: labels.uploadRequired,
    },
  });

  const saveLabel = form.saving ? labels.saving : form.uploading ? labels.uploading : labels.save;

  return (
    <form
      className="space-y-8"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        form.save();
      }}
    >
      <section className="space-y-2" aria-labelledby="presentation-bio-heading">
        <h2 id="presentation-bio-heading" className="text-base font-medium">
          {labels.bio}
        </h2>
        <label htmlFor="presentation-bio" className="sr-only">
          {labels.bio}
        </label>
        <textarea
          id="presentation-bio"
          className={`${FIELD_CLASS} min-h-36 resize-y`}
          maxLength={2000}
          value={form.bio}
          onChange={(event) => {
            form.setBio(event.target.value);
          }}
        />
        <p className="text-muted-foreground text-xs" aria-live="polite">
          {form.bio.length}/2000
        </p>
      </section>

      <section className="space-y-4" aria-labelledby="presentation-media-heading">
        <header className="space-y-1">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="presentation-media-heading" className="text-base font-medium">
              {labels.media}
            </h2>
            <p className="text-muted-foreground text-xs">
              {labels.mediaCount
                .replace("{count}", String(form.media.length))
                .replace("{max}", "5")}
            </p>
          </div>
          <p className="text-muted-foreground text-sm">{labels.help}</p>
          <p className="text-muted-foreground text-xs leading-relaxed">{labels.requirements}</p>
        </header>

        <ul className="space-y-4">
          {form.media.map((item, index) => (
            <li key={item.clientKey}>
              <MediaItemEditor
                index={index}
                item={item}
                labels={labels}
                fieldClass={FIELD_CLASS}
                previewSrc={form.previewSrc(item)}
                busy={form.pending}
                onPatch={(patch) => {
                  form.patchMedia(index, patch);
                }}
                onFile={(file) => {
                  form.onFile(index, file);
                }}
                onRetry={() => {
                  form.retryUpload(index);
                }}
                onRemove={() => {
                  form.removeMedia(index);
                }}
              />
            </li>
          ))}
        </ul>

        {form.canAdd ? (
          <Button
            type="button"
            variant="outline"
            className="min-h-11"
            onClick={form.addMedia}
            disabled={form.pending}
          >
            {labels.addMedia}
          </Button>
        ) : null}
      </section>

      <div
        className="border-border bg-background/95 sticky bottom-0 z-10 -mx-1 space-y-3 border-t px-1 py-4 backdrop-blur-sm"
        role="region"
        aria-label={labels.save}
      >
        {form.error ? (
          <p className="text-destructive text-sm" role="alert">
            {form.error}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="submit"
            className="min-h-11 min-w-44"
            disabled={form.pending}
            aria-busy={form.pending}
          >
            {saveLabel}
          </Button>
          <p role="status" className="text-muted-foreground text-sm" aria-live="polite">
            {form.message}
          </p>
        </div>
      </div>
    </form>
  );
}
