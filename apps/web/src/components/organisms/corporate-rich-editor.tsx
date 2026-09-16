"use client";

/* eslint-disable max-lines-per-function */

import { useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";

import { corporateMutationAction } from "@/actions/corporate";
import { updateCorporatePresentationAction } from "@/actions/corporate-detail";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { EntityEditorField, EntityEditorLayout } from "@/components/molecules/entity-editor-layout";
import { EntityLinksEditor } from "@/components/molecules/entity-links-editor";
import { MarkdownEditor } from "@/components/molecules/markdown-editor";
import {
  PresentationMediaEditor,
  type PresentationMediaEditorLabels,
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
import {
  ENTITY_EDITOR_CONFIGS,
  validateEntityDisplayName,
  validateEntityLinks,
} from "@/lib/entity-editor-contract";
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
  const [pending, startTransition] = useTransition();
  const saveReceipt = useRef<{ payload: string; key: string } | null>(null);
  const uploadReceipts = useRef(new Map<string, { file: File; key: string }>());
  const uploadGeneration = useRef(new Map<string, number>());
  const router = useRouter();
  const config = ENTITY_EDITOR_CONFIGS[entityUpdate.kind];
  if (!initial.can_edit) return null;

  function patchMedia(index: number, patch: Partial<PresentationMediaDraft>) {
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
      patchMedia(index, {
        uploadState: "error",
        itemError: objects(reason === "size" ? "mediaSizeExceeded" : "mediaUnsupportedType"),
      });
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
    } catch {
      if (uploadGeneration.current.get(clientKey) !== generation) return;
      patchMediaByKey(clientKey, {
        uploadState: "error",
        pendingFile: file,
        itemError: objects("mediaUploadFailed"),
      });
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
    const nameError = validateEntityDisplayName(name, config.limits.displayName);
    const linksError = validateEntityLinks(links, config.limits.links);
    const activeMedia = media.filter(
      (item) => item.url || item.localPreview || item.pendingFile || item.alt || item.caption,
    );
    if (nameError || linksError || activeMedia.some((item) => item.uploadState !== "ready")) {
      setError(nameError ?? linksError ?? objects("mediaUploadRequired"));
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
    if (!corporatePresentationSchema.safeParse(candidate).success) {
      setError(objects("mediaInvalid"));
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
    startTransition(async () => {
      try {
        const entityResult = await updateEntity(key);
        if (!entityResult.ok) {
          setError(entityResult.message);
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
          setError(result.ok ? account("profileSaveFailed") : result.message);
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
              >
                <Input
                  id="entity-name"
                  value={name}
                  required
                  maxLength={config.limits.displayName}
                  onChange={(event) => {
                    setName(event.target.value);
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
                onChange={setDescription}
                onModeChange={setDescriptionMode}
                maxLength={config.limits.description}
                hint={account("profileBioHint")}
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
                  setMedia((items) => items.filter((_, itemIndex) => itemIndex !== index));
                }}
                moveMedia={(from, to) => {
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
                onChange={setLinks}
              />
            ),
          }}
          afterBlocks={
            <>
              {error ? (
                <p role="alert" className="text-destructive text-sm">
                  {error}
                </p>
              ) : null}
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

function mediaEditorLabels(
  t: ReturnType<typeof useTranslations<"objects">>,
): PresentationMediaEditorLabels {
  return {
    media: t("media"),
    help: t("mediaHelp"),
    requirements: t("mediaRequirements"),
    mediaCount: "{count} / {max}",
    addMedia: t("addMedia"),
    moveUp: t("mediaMoveUp"),
    moveDown: t("mediaMoveDown"),
    remove: t("removeMedia"),
    kind: t("mediaKind"),
    alt: t("mediaAlt"),
    caption: t("mediaCaption"),
    upload: t("mediaUpload"),
    uploading: t("mediaUploading"),
    youtubeHint: t("mediaYoutubeHint"),
    githubHint: t("mediaGithubHint"),
    youtubePlaceholder: "dQw4w9WgXcQ",
    githubPlaceholder: "https://raw.githubusercontent.com/owner/repo/commit/file.png",
    preview: t("mediaPreview"),
    retryUpload: t("mediaRetryUpload"),
    replaceUpload: t("mediaReplaceUpload"),
    sourceUpload: t("mediaSourceUpload"),
    sourceGithub: t("mediaSourceGithub"),
    sourceYoutube: t("mediaSourceYoutube"),
    sourceChoice: t("mediaSourceChoice"),
    sourceUrl: t("mediaSourceUrl"),
    urlHint: t("mediaUrlHint"),
    urlPlaceholder: t("mediaUrlPlaceholder"),
    uploadedReady: t("mediaUploadedReady"),
    itemStatusIdle: t("mediaItemStatusIdle"),
    itemStatusUploading: t("mediaItemStatusUploading"),
    itemStatusReady: t("mediaItemStatusReady"),
    itemStatusError: t("mediaItemStatusError"),
    altRequired: t("mediaAltRequired"),
    invalid: t("mediaInvalid"),
    kindImage: t("mediaKindImage"),
    kindVideo: t("mediaKindVideo"),
  };
}
