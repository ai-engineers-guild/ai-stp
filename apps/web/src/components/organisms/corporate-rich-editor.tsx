"use client";

/* eslint-disable max-lines -- coordinates shared upload and two mutation boundaries */
/* eslint-disable max-lines-per-function */

import { useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";

import { corporateMutationAction } from "@/actions/corporate";
import { updateCorporatePresentationAction } from "@/actions/corporate-detail";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import {
  EntityEditorErrorSummary,
  EntityEditorField,
  EntityEditorLayout,
} from "@/components/molecules/entity-editor-layout";
import { EntityLinksEditor } from "@/components/molecules/entity-links-editor";
import { MarkdownEditor } from "@/components/molecules/markdown-editor";
import {
  PresentationMediaEditor,
  mediaEditorLabels,
} from "@/components/organisms/presentation-media-editor";
import {
  emptyPresentationMediaItem,
  presentationMediaItemFromInitial,
  previewSrc,
  readLocalMediaPreview,
  type PresentationMediaDraft,
} from "@/components/organisms/use-object-presentation-form";
import type { TechnologyMetadata } from "@/lib/api/generated/types.gen";
import { kindFromMime, validateComponentMediaFile } from "@/lib/component-media";
import {
  corporatePresentationSchema,
  entityProfileViewSchema,
  type CorporateDetailResource,
  type CorporatePresentation,
} from "@/lib/corporate-detail";
import { uploadCorporateDetailMedia } from "@/lib/corporate-detail-upload";
import { ENTITY_EDITOR_CONFIGS, validateEntityFieldErrors } from "@/lib/entity-editor-contract";
import {
  fieldErrorsFromIssues,
  formatCorporateFieldPath,
  localizeCorporateFieldErrors,
  withoutFieldErrors,
  type FieldErrors,
} from "@/lib/api/field-errors";
import { useRouter } from "@/lib/i18n/navigation";

export type CorporateEntityUpdate =
  | { kind: "project"; revision: number; state: "active" | "archived" }
  | {
      kind: "team";
      revision: number;
      state: "active" | "archived";
      description: string;
    }
  | { kind: "technology"; revision: number; metadata: TechnologyMetadata };

export function CorporateRichEditor({
  initial,
  organizationId,
  resource,
  resourceId,
  csrfToken,
  cancelHref,
  entityUpdate,
}: {
  initial: CorporatePresentation;
  organizationId: string;
  resource: CorporateDetailResource;
  resourceId: string;
  csrfToken: string;
  cancelHref: string;
  entityUpdate: CorporateEntityUpdate;
}) {
  const account = useTranslations("account");
  const common = useTranslations("common");
  const corporate = useTranslations("corporate");
  const objects = useTranslations("objects");
  const [name, setName] = useState(initial.name);
  const [description, setDescription] = useState(initial.description);
  const [links, setLinks] = useState(initial.links);
  const [media, setMedia] = useState<PresentationMediaDraft[]>(() =>
    initial.media.length
      ? initial.media.map(presentationMediaItemFromInitial)
      : [emptyPresentationMediaItem()],
  );
  const [descriptionMode, setDescriptionMode] = useState<"write" | "preview">("write");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [pending, startTransition] = useTransition();
  const saveReceipt = useRef<{ payload: string; key: string } | null>(null);
  const uploadReceipts = useRef(new Map<string, { file: File; key: string }>());
  const uploadGeneration = useRef(new Map<string, number>());
  const router = useRouter();
  const config = ENTITY_EDITOR_CONFIGS[entityUpdate.kind];
  if (!initial.can_edit) return null;

  const fieldErrorMessages = corporateFieldErrorMessages(account, corporate, objects);

  function clearFieldErrors(prefixes: string[]) {
    setFieldErrors((current) => withoutFieldErrors(current, prefixes));
  }

  function patchMedia(index: number, patch: Partial<PresentationMediaDraft>) {
    clearFieldErrors([`media.${index}`, `media[${index}]`]);
    setMedia((items) =>
      items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    );
  }

  function patchMediaByKey(clientKey: string, patch: Partial<PresentationMediaDraft>) {
    setMedia((items) =>
      items.map((item) => (item.clientKey === clientKey ? { ...item, ...patch } : item)),
    );
  }

  async function upload(index: number, file: File | null) {
    if (!file) return;
    const item = media[index];
    if (!item) return;
    const reason = validateComponentMediaFile(file);
    if (reason) {
      const message = objects(reason === "size" ? "mediaSizeExceeded" : "mediaUnsupportedType");
      patchMedia(index, {
        uploadState: "error",
        itemError: message,
      });
      setFieldErrors((current) => ({ ...current, [`media.${index}.url`]: message }));
      return;
    }
    const kind = kindFromMime(file.type);
    if (!kind) return;
    const clientKey = item.clientKey;
    const generation = (uploadGeneration.current.get(clientKey) ?? 0) + 1;
    uploadGeneration.current.set(clientKey, generation);
    patchMedia(index, {
      kind,
      uploadState: "uploading",
      pendingFile: file,
      itemError: null,
      url: "",
    });
    void readLocalMediaPreview(file).then((localPreview) => {
      if (uploadGeneration.current.get(clientKey) === generation)
        patchMediaByKey(clientKey, { localPreview });
    });
    const previous = uploadReceipts.current.get(clientKey);
    const key = previous?.file === file ? previous.key : crypto.randomUUID();
    uploadReceipts.current.set(clientKey, { file, key });
    try {
      const result = await uploadCorporateDetailMedia(
        {
          organizationId,
          resource,
          resourceId,
          csrfToken,
          purpose: "media",
          expectedRevision: initial.revision,
          authorizationRevision: initial.authorization_revision,
          idempotencyKey: key,
        },
        file,
      );
      if (uploadGeneration.current.get(clientKey) !== generation) return;
      patchMediaByKey(clientKey, {
        kind: result.kind,
        url: result.public_url,
        uploadState: "ready",
        pendingFile: null,
        itemError: null,
      });
      clearFieldErrors([`media.${index}`, `media[${index}]`]);
    } catch {
      if (uploadGeneration.current.get(clientKey) !== generation) return;
      patchMediaByKey(clientKey, {
        uploadState: "error",
        pendingFile: file,
        itemError: objects("mediaUploadFailed"),
      });
      setFieldErrors((current) => ({
        ...current,
        [`media.${index}.url`]: objects("mediaUploadFailed"),
      }));
    }
  }

  async function updateEntity(key: string) {
    if (name.trim() === initial.name) return { ok: true } as const;
    const base = {
      schema_version: 1 as const,
      expected_revision: entityUpdate.revision,
      authorization_revision: initial.authorization_revision,
      idempotency_key: `${key}.entity`,
    };
    const request =
      entityUpdate.kind === "technology"
        ? {
            method: "PUT" as const,
            path: `/v1/corporate/organizations/${organizationId}/technologies/${resourceId}`,
            body: { ...base, metadata: { ...entityUpdate.metadata, name: name.trim() } },
          }
        : {
            method: "PATCH" as const,
            path: `/v1/corporate/organizations/${organizationId}/${resource}/${resourceId}`,
            body: {
              ...base,
              name: name.trim(),
              state: entityUpdate.state,
              ...(entityUpdate.kind === "team" ? { description: entityUpdate.description } : {}),
            },
          };
    return corporateMutationAction({ csrfToken, organizationId, ...request });
  }

  function save() {
    const validationErrors = validateEntityFieldErrors(name, links, config.limits, {
      displayNameRequired: account("profileErrorDisplayNameRequired"),
      displayNameTooLong: account("profileErrorDisplayNameTooLong"),
      tooManyLinks: account("profileErrorTooManyLinks"),
      linkLabelRequired: account("profileErrorLinkLabelRequired"),
      linkLabelTooLong: account("profileErrorLinkLabelTooLong"),
      linkUrl: account("profileErrorLinkUrl"),
      duplicateLink: account("profileErrorDuplicateLink"),
    });
    const activeMedia = media.filter(
      (item) => item.url || item.localPreview || item.pendingFile || item.alt || item.caption,
    );
    activeMedia.forEach((item) => {
      const index = media.indexOf(item);
      if (item.uploadState !== "ready")
        validationErrors[`media.${index}.url`] = objects("mediaUploadRequired");
      if (!item.alt.trim()) validationErrors[`media.${index}.alt`] = objects("mediaAltRequired");
    });
    if (Object.keys(validationErrors).length) {
      setFieldErrors(validationErrors);
      setError(Object.values(validationErrors)[0] ?? objects("mediaInvalid"));
      return;
    }
    const presentationMedia = activeMedia.map(({ kind, url, alt, caption }) => ({
      kind,
      url,
      alt: alt.trim(),
      caption: caption.trim(),
    }));
    const candidate = {
      ...initial,
      name: name.trim(),
      description,
      links,
      media: activeMedia.map((item) => ({
        kind: item.kind,
        url: item.url,
        alt: item.alt,
        caption: item.caption,
        source_label: name.trim(),
        id: item.clientKey,
      })),
    };
    const parsedCandidate = corporatePresentationSchema.safeParse(candidate);
    if (!parsedCandidate.success) {
      const candidateErrors = localizeCorporateFieldErrors(
        fieldErrorsFromIssues(parsedCandidate.error.issues),
        fieldErrorMessages,
      );
      setFieldErrors(candidateErrors);
      setError(Object.values(candidateErrors)[0] ?? objects("mediaInvalid"));
      return;
    }
    const payload = JSON.stringify({
      name: name.trim(),
      description,
      links,
      media: presentationMedia,
    });
    if (saveReceipt.current?.payload !== payload)
      saveReceipt.current = { payload, key: crypto.randomUUID() };
    const key = saveReceipt.current.key;
    setError(null);
    setFieldErrors({});
    startTransition(async () => {
      try {
        const entityResult = await updateEntity(key);
        if (!entityResult.ok) {
          const errors = localizeCorporateFieldErrors(entityResult.fieldErrors, fieldErrorMessages);
          setFieldErrors(errors);
          setError(Object.values(errors)[0] ?? entityResult.message);
          return;
        }
        const result = await updateCorporatePresentationAction({
          organizationId,
          csrfToken,
          resource,
          resourceId,
          data: {
            schema_version: 1,
            fields: { description, links, avatar_asset_id: null, media: presentationMedia },
            expected_revision: initial.revision,
            authorization_revision: initial.authorization_revision,
            idempotency_key: key,
          },
        });
        if (!result.ok || !entityProfileViewSchema.safeParse(result.data).success) {
          const errors = result.ok
            ? {}
            : localizeCorporateFieldErrors(result.fieldErrors, fieldErrorMessages);
          setFieldErrors(errors);
          setError(
            Object.values(errors)[0] ?? (result.ok ? account("profileSaveFailed") : result.message),
          );
          return;
        }
        saveReceipt.current = null;
        router.push(cancelHref);
        router.refresh();
      } catch {
        setError(account("profileSaveFailed"));
      }
    });
  }

  const mediaLabels = mediaEditorLabels(objects);
  return (
    <form
      aria-label={objects("editPresentation")}
      onSubmit={(event) => {
        event.preventDefault();
        save();
      }}
    >
      <fieldset disabled={pending} className="min-w-0">
        <EntityEditorLayout
          config={config}
          title={corporate("publicPresentation")}
          description={corporate("publicPresentationEditHintNoAvatar")}
          blocks={{
            displayName: (
              <EntityEditorField
                label={account("profileDisplayName")}
                htmlFor="entity-name"
                required
                error={fieldErrors.name}
              >
                <Input
                  id="entity-name"
                  value={name}
                  required
                  maxLength={config.limits.displayName}
                  className={
                    fieldErrors.name
                      ? "border-destructive focus-visible:ring-destructive"
                      : undefined
                  }
                  aria-invalid={Boolean(fieldErrors.name)}
                  aria-describedby={fieldErrors.name ? "entity-name-error" : undefined}
                  onChange={(event) => {
                    setName(event.target.value);
                    clearFieldErrors(["name"]);
                  }}
                />
              </EntityEditorField>
            ),
            description: (
              <MarkdownEditor
                id="entity-description"
                label={corporate("description")}
                value={description}
                mode={descriptionMode}
                onChange={(value) => {
                  setDescription(value);
                  clearFieldErrors(["description"]);
                }}
                onModeChange={setDescriptionMode}
                maxLength={config.limits.description}
                hint={account("profileBioHint")}
                error={fieldErrors.description}
                labels={{
                  write: account("profileBioPlain"),
                  preview: account("profileBioRender"),
                }}
              />
            ),
            media: (
              <PresentationMediaEditor
                media={media}
                labels={mediaLabels}
                pending={pending}
                max={config.limits.media}
                previewSrc={previewSrc}
                patchMedia={patchMedia}
                onFile={(index, file) => void upload(index, file)}
                retryUpload={(index) => void upload(index, media[index]?.pendingFile ?? null)}
                removeMedia={(index) => {
                  clearFieldErrors(["media.", "media["]);
                  setMedia((items) => items.filter((_, itemIndex) => itemIndex !== index));
                }}
                moveMedia={(from, to) => {
                  clearFieldErrors(["media."]);
                  setMedia((items) => {
                    const next = [...items];
                    const [item] = next.splice(from, 1);
                    if (!item) return items;
                    next.splice(to, 0, item);
                    return next;
                  });
                }}
                addMedia={() => {
                  setMedia((items) =>
                    items.length >= config.limits.media
                      ? items
                      : [...items, emptyPresentationMediaItem()],
                  );
                }}
                fieldErrors={fieldErrors}
              />
            ),
            links: (
              <EntityLinksEditor
                links={links}
                max={config.limits.links}
                labels={{
                  title: account("profileLinks"),
                  add: account("profileAddLink"),
                  empty: account("profileLinksEmpty"),
                  label: account("linkLabel"),
                  url: account("linkUrl"),
                  remove: account("profileRemoveLink"),
                }}
                onChange={(value) => {
                  setLinks(value);
                  clearFieldErrors(["links"]);
                }}
                fieldErrors={fieldErrors}
              />
            ),
          }}
          afterBlocks={
            <>
              <EntityEditorErrorSummary
                error={error}
                fieldErrors={fieldErrors}
                summary={account("profileErrorFieldSummary")}
                fieldLabel={(path) => formatCorporateFieldPath(path, fieldErrorMessages.labels)}
              />
              <div className="border-border flex flex-col-reverse gap-2 border-t pt-4 sm:flex-row sm:justify-end">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    router.push(cancelHref);
                  }}
                >
                  {common("cancel")}
                </Button>
                <Button type="submit" disabled={pending}>
                  {pending ? common("loading") : account("profileSave")}
                </Button>
              </div>
            </>
          }
        />
      </fieldset>
    </form>
  );
}

function corporateFieldErrorMessages(
  account: ReturnType<typeof useTranslations<"account">>,
  corporate: ReturnType<typeof useTranslations<"corporate">>,
  objects: ReturnType<typeof useTranslations<"objects">>,
) {
  return {
    displayName: account("profileErrorDisplayNameInvalid"),
    description: account("profileErrorDescription"),
    tooManyLinks: account("profileErrorTooManyLinks"),
    linkLabel: account("profileErrorLinkLabelInvalid"),
    linkUrl: account("profileErrorLinkUrl"),
    mediaSource: account("profileErrorMediaSource"),
    mediaAlt: objects("mediaAltRequired"),
    labels: {
      displayName: account("profileDisplayName"),
      description: corporate("description"),
      links: account("profileLinks"),
      label: account("linkLabel"),
      media: objects("media"),
      url: account("linkUrl"),
      alt: objects("mediaAlt"),
      kind: objects("mediaKind"),
    },
  };
}
