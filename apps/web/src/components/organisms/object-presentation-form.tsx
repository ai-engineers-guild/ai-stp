"use client";

import type { ReactNode } from "react";
import { useState } from "react";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { EntityEditorField, EntityEditorLayout } from "@/components/molecules/entity-editor-layout";
import { MarkdownEditor } from "@/components/molecules/markdown-editor";
import { PresentationMediaEditor } from "@/components/organisms/presentation-media-editor";
import { useObjectPresentationForm } from "@/components/organisms/use-object-presentation-form";
import type { OwnerPresentationMedia } from "@/lib/api/owner";
import { ENTITY_EDITOR_CONFIGS } from "@/lib/entity-editor-contract";

type Labels = {
  editorTitle?: string;
  editorDescription?: string;
  displayName?: string;
  displayNameHint?: string;
  markdownWrite?: string;
  markdownPreview?: string;
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
  sourceUrl?: string;
  urlHint?: string;
  urlPlaceholder?: string;
  uploadedReady: string;
  uploadError: string;
  itemStatusIdle: string;
  itemStatusUploading: string;
  itemStatusReady: string;
  itemStatusError: string;
  altRequired: string;
  kindImage: string;
  kindVideo: string;
  kindYoutube: string;
  mediaCount: string;
  moveUp?: string;
  moveDown?: string;
};

export function ObjectPresentationForm({
  locale,
  stableId,
  objectKind = "component",
  csrfToken,
  initialBio,
  initialMedia,
  initialDisplayName,
  labels,
  beforeMedia,
}: {
  objectKind?: "component" | "setup" | undefined;
  locale: string;
  stableId: string;
  csrfToken: string;
  initialBio: string;
  initialMedia: OwnerPresentationMedia[];
  initialDisplayName?: string;
  labels: Labels;
  beforeMedia?: ReactNode;
}) {
  const form = useObjectPresentationForm({
    objectKind,
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
  const [bioMode, setBioMode] = useState<"write" | "preview">("write");

  const saveLabel = form.saving ? labels.saving : form.uploading ? labels.uploading : labels.save;

  const config = ENTITY_EDITOR_CONFIGS[objectKind];

  return (
    <form
      className="min-w-0"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        form.save();
      }}
    >
      <EntityEditorLayout
        config={config}
        title={labels.editorTitle ?? labels.bio}
        description={labels.editorDescription}
        blocks={{
          displayName: (
            <EntityEditorField
              label={labels.displayName ?? "Display name"}
              htmlFor="presentation-display-name"
              hint={labels.displayNameHint}
            >
              <Input
                id="presentation-display-name"
                value={initialDisplayName ?? ""}
                readOnly
                aria-readonly="true"
              />
            </EntityEditorField>
          ),
          description: (
            <MarkdownEditor
              id="presentation-bio"
              label={labels.bio}
              value={form.bio}
              mode={bioMode}
              onChange={form.setBio}
              onModeChange={setBioMode}
              maxLength={config.limits.description}
              error={form.fieldErrors.bio}
              labels={{
                write: labels.markdownWrite ?? "Write",
                preview: labels.markdownPreview ?? "Preview",
              }}
            />
          ),
          media: (
            <>
              {beforeMedia}
              <PresentationMediaEditor
                media={form.media}
                labels={{
                  ...labels,
                  moveUp: labels.moveUp ?? "Move up",
                  moveDown: labels.moveDown ?? "Move down",
                }}
                pending={form.pending}
                max={config.limits.media}
                previewSrc={form.previewSrc}
                patchMedia={form.patchMedia}
                onFile={form.onFile}
                retryUpload={form.retryUpload}
                removeMedia={form.removeMedia}
                moveMedia={form.moveMedia}
                addMedia={form.addMedia}
                fieldErrors={form.fieldErrors}
              />
            </>
          ),
        }}
        afterBlocks={
          <div
            className="border-border bg-background/95 sticky bottom-0 z-10 -mx-1 space-y-3 border-t px-1 py-4 backdrop-blur-sm"
            role="region"
            aria-label={labels.save}
          >
            {form.error ? (
              <div
                className="border-destructive/60 bg-destructive/10 rounded-md border p-3"
                role="alert"
              >
                <p className="text-destructive text-sm font-medium">{form.error}</p>
                {form.errorCode ? (
                  <code className="text-muted-foreground mt-1 block text-xs">{form.errorCode}</code>
                ) : null}
              </div>
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
        }
      />
    </form>
  );
}
