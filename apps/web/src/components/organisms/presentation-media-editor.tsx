"use client";

import { Button } from "@/components/atoms/button";
import { EntityEditorSection } from "@/components/molecules/entity-editor-layout";
import {
  MediaItemEditor,
  type MediaItemLabels,
} from "@/components/organisms/object-presentation-media-item";
import type { PresentationMediaDraft } from "@/components/organisms/use-object-presentation-form";

const FIELD_CLASS =
  "border-input bg-background focus-visible:ring-ring min-h-11 w-full rounded-sm border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60";

export type PresentationMediaEditorLabels = MediaItemLabels & {
  media: string;
  help: string;
  requirements: string;
  mediaCount: string;
  addMedia: string;
  moveUp: string;
  moveDown: string;
};

export function PresentationMediaEditor({
  media,
  labels,
  pending,
  max = 5,
  previewSrc,
  patchMedia,
  onFile,
  retryUpload,
  removeMedia,
  moveMedia,
  addMedia,
  fieldErrors = {},
}: {
  media: PresentationMediaDraft[];
  labels: PresentationMediaEditorLabels;
  pending: boolean;
  max?: number;
  previewSrc: (item: PresentationMediaDraft) => string | null;
  patchMedia: (index: number, patch: Partial<PresentationMediaDraft>) => void;
  onFile: (index: number, file: File | null) => void;
  retryUpload: (index: number) => void;
  removeMedia: (index: number) => void;
  moveMedia: (from: number, to: number) => void;
  addMedia: () => void;
  fieldErrors?: Record<string, string>;
}) {
  return (
    <EntityEditorSection title={labels.media} description={labels.help}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-muted-foreground text-xs leading-relaxed">{labels.requirements}</p>
        <p className="text-muted-foreground text-xs">
          {labels.mediaCount.replace("{count}", String(media.length)).replace("{max}", String(max))}
        </p>
      </div>
      <ul className="space-y-4">
        {media.map((item, index) => (
          <li key={item.clientKey}>
            <div className="mb-2 flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={pending || index === 0}
                onClick={() => {
                  moveMedia(index, index - 1);
                }}
              >
                {labels.moveUp}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={pending || index === media.length - 1}
                onClick={() => {
                  moveMedia(index, index + 1);
                }}
              >
                {labels.moveDown}
              </Button>
            </div>
            <MediaItemEditor
              index={index}
              item={item}
              labels={labels}
              fieldClass={FIELD_CLASS}
              previewSrc={previewSrc(item)}
              busy={pending}
              onPatch={(patch) => {
                patchMedia(index, patch);
              }}
              onFile={(file) => {
                onFile(index, file);
              }}
              onRetry={() => {
                retryUpload(index);
              }}
              onRemove={() => {
                removeMedia(index);
              }}
              errors={{
                url: fieldErrors[`media.${index}.url`] ?? fieldErrors[`media[${index}].url`],
                alt: fieldErrors[`media.${index}.alt`] ?? fieldErrors[`media[${index}].alt`],
                item:
                  fieldErrors[`media.${index}`] ??
                  fieldErrors[`media[${index}]`] ??
                  fieldErrors[`media.${index}.kind`],
              }}
            />
          </li>
        ))}
      </ul>
      {media.length < max ? (
        <Button
          type="button"
          variant="outline"
          className="min-h-11"
          onClick={addMedia}
          disabled={pending}
        >
          {labels.addMedia}
        </Button>
      ) : null}
    </EntityEditorSection>
  );
}
