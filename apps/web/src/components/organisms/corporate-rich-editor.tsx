"use client";

import { useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { updateCorporatePresentationAction } from "@/actions/corporate-detail";
import { uploadCorporateDetailMedia } from "@/lib/corporate-detail-upload";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import { MarkdownDescription } from "@/components/molecules/markdown-description";
import {
  corporatePresentationSchema,
  entityProfileViewSchema,
  type CorporatePresentation,
  type CorporateDetailResource,
} from "@/lib/corporate-detail";
import { useRouter } from "@/lib/i18n/navigation";

// One form owns the draft, revision and retry receipts across all presentation fields.
// eslint-disable-next-line max-lines-per-function
export function CorporateRichEditor({
  initial,
  organizationId,
  resource,
  resourceId,
  csrfToken,
}: {
  initial: CorporatePresentation;
  organizationId: string;
  resource: CorporateDetailResource;
  resourceId: string;
  csrfToken: string;
}) {
  const t = useTranslations("account");
  const c = useTranslations("common");
  const corporate = useTranslations("corporate");
  const objects = useTranslations("objects");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(initial);
  const [preview, setPreview] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const receipt = useRef<{ payload: string; key: string } | null>(null);
  const uploadReceipt = useRef<{ file: File; purpose: string; key: string } | null>(null);
  const router = useRouter();
  if (!initial.can_edit) return null;
  if (!editing)
    return (
      <Button
        variant="outline"
        size="lg"
        className="min-h-11 w-full"
        onClick={() => {
          setDraft(initial);
          setError(null);
          setEditing(true);
        }}
      >
        {t("editProfile")}
      </Button>
    );

  function save() {
    const parsed = corporatePresentationSchema.safeParse(draft);
    if (!parsed.success) {
      setError(t("profileSaveFailed"));
      return;
    }
    const data = {
      schema_version: 1,
      fields: {
        description: draft.description,
        links: draft.links,
        avatar_asset_id: draft.avatar_asset_id,
        media: draft.media.map(({ kind, url, alt, caption }) => ({ kind, url, alt, caption })),
      },
      expected_revision: initial.revision,
      authorization_revision: initial.authorization_revision,
    };
    const payload = JSON.stringify(data);
    if (receipt.current?.payload !== payload)
      receipt.current = { payload, key: crypto.randomUUID() };
    const idempotency_key = receipt.current.key;
    setError(null);
    startTransition(async () => {
      try {
        const result = await updateCorporatePresentationAction({
          organizationId,
          csrfToken,
          resource,
          resourceId,
          data: { ...data, idempotency_key },
        });
        if (!result.ok) {
          setError(result.message);
          return;
        }
        // Only an acknowledged persisted presentation closes the editor.
        if (!entityProfileViewSchema.safeParse(result.data).success) {
          setError(t("profileSaveFailed"));
          return;
        }
        receipt.current = null;
        setEditing(false);
        router.refresh();
      } catch {
        setError(t("profileSaveFailed"));
      }
    });
  }

  function upload(file: File | undefined, purpose: "avatar" | "media") {
    if (!file) return;
    if (uploadReceipt.current?.file !== file || uploadReceipt.current.purpose !== purpose)
      uploadReceipt.current = { file, purpose, key: crypto.randomUUID() };
    const idempotencyKey = uploadReceipt.current.key;
    setError(null);
    startTransition(async () => {
      try {
        const result = await uploadCorporateDetailMedia(
          {
            organizationId,
            resource,
            resourceId,
            csrfToken,
            purpose,
            expectedRevision: initial.revision,
            authorizationRevision: initial.authorization_revision,
            idempotencyKey,
          },
          file,
        );
        const { avatar_asset_id: asset_id, public_url } = result;
        setDraft((current) =>
          purpose === "avatar"
            ? { ...current, avatar_asset_id: asset_id, avatar_url: public_url }
            : {
                ...current,
                media: [
                  ...current.media,
                  {
                    id: asset_id,
                    url: public_url,
                    kind: file.type.startsWith("video/") ? "video" : "image",
                    alt: file.name,
                    caption: "",
                    source_label: current.name,
                  },
                ],
              },
        );
      } catch {
        setError(t("profileAvatarFailed"));
      }
    });
  }

  return (
    <form
      aria-label={objects("editPresentation")}
      className="border-border bg-card w-full min-w-0 space-y-6 rounded-lg border p-5 shadow-sm sm:p-6"
      onSubmit={(event) => {
        event.preventDefault();
        save();
      }}
    >
      <fieldset disabled={pending} className="min-w-0 space-y-5">
        <header className="border-border space-y-1 border-b pb-4">
          <h2 className="text-xl font-medium tracking-tight">{objects("editPresentation")}</h2>
          <p className="text-muted-foreground text-sm leading-relaxed">
            {objects("editPresentationNote")}
          </p>
        </header>
        <div className="space-y-2">
          <Label htmlFor="entity-avatar">{t("profileUpload")}</Label>
          <Input
            id="entity-avatar"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(event) => {
              upload(event.target.files?.[0], "avatar");
              event.target.value = "";
            }}
          />
          <p className="text-muted-foreground text-xs">{t("profileAvatarRequirements")}</p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="entity-media">{objects("mediaUpload")}</Label>
          <Input
            id="entity-media"
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif,video/mp4,video/webm"
            disabled={draft.media.length >= 5}
            onChange={(event) => {
              upload(event.target.files?.[0], "media");
              event.target.value = "";
            }}
          />
          {draft.media.map((item) => (
            <div key={item.id} className="space-y-2">
              <Label htmlFor={`entity-media-${item.id}`}>{objects("mediaAlt")}</Label>
              <Input
                id={`entity-media-${item.id}`}
                value={item.alt}
                required
                maxLength={240}
                onChange={(event) => {
                  setDraft({
                    ...draft,
                    media: draft.media.map((media) =>
                      media.id === item.id ? { ...media, alt: event.target.value } : media,
                    ),
                  });
                }}
              />
              <Label htmlFor={`entity-caption-${item.id}`}>{objects("mediaCaption")}</Label>
              <Input
                id={`entity-caption-${item.id}`}
                value={item.caption}
                maxLength={500}
                onChange={(event) => {
                  setDraft({
                    ...draft,
                    media: draft.media.map((media) =>
                      media.id === item.id ? { ...media, caption: event.target.value } : media,
                    ),
                  });
                }}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setDraft({
                    ...draft,
                    media: draft.media.filter((media) => media.id !== item.id),
                  });
                }}
              >
                {objects("removeMedia")}
              </Button>
            </div>
          ))}
        </div>
        <div className="space-y-2">
          <Label htmlFor="entity-name">{t("profileDisplayName")}</Label>
          <Input id="entity-name" value={draft.name} readOnly />
        </div>
        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Label htmlFor="entity-description">{corporate("description")}</Label>
            <div
              className="border-border bg-muted/40 inline-flex rounded-sm border p-0.5"
              role="group"
              aria-label={t("profileBioMode")}
            >
              <Button
                type="button"
                variant={!preview ? "secondary" : "ghost"}
                size="sm"
                aria-pressed={!preview}
                onClick={() => {
                  setPreview(false);
                }}
              >
                {t("profileBioPlain")}
              </Button>
              <Button
                type="button"
                variant={preview ? "secondary" : "ghost"}
                size="sm"
                aria-pressed={preview}
                onClick={() => {
                  setPreview(true);
                }}
              >
                {t("profileBioRender")}
              </Button>
            </div>
          </div>
          {preview ? (
            <MarkdownDescription source={draft.description} heading={t("profilePreview")} />
          ) : (
            <Textarea
              id="entity-description"
              className="min-h-40 font-mono"
              value={draft.description}
              maxLength={20000}
              onChange={(event) => {
                setDraft({ ...draft, description: event.target.value });
              }}
            />
          )}
          <p className="text-muted-foreground text-xs">{t("profileBioHint")}</p>
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-medium">{t("profileLinks")}</h2>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={draft.links.length >= 8}
              onClick={() => {
                setDraft({ ...draft, links: [...draft.links, { label: "", url: "https://" }] });
              }}
            >
              {t("profileAddLink")}
            </Button>
          </div>
          {draft.links.map((link, index) => (
            <div key={index} className="space-y-2">
              <Label htmlFor={`entity-link-label-${index}`}>{t("linkLabel")}</Label>
              <Input
                id={`entity-link-label-${index}`}
                value={link.label}
                required
                maxLength={60}
                onChange={(event) => {
                  setDraft({
                    ...draft,
                    links: draft.links.map((item, i) =>
                      i === index ? { ...item, label: event.target.value } : item,
                    ),
                  });
                }}
              />
              <Label htmlFor={`entity-link-url-${index}`}>{t("linkUrl")}</Label>
              <Input
                id={`entity-link-url-${index}`}
                type="url"
                value={link.url}
                required
                onChange={(event) => {
                  setDraft({
                    ...draft,
                    links: draft.links.map((item, i) =>
                      i === index ? { ...item, url: event.target.value } : item,
                    ),
                  });
                }}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDraft({ ...draft, links: draft.links.filter((_, i) => i !== index) });
                }}
              >
                {t("profileRemoveLink")}
              </Button>
            </div>
          ))}
        </div>
        {draft.avatar_asset_id ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setDraft({ ...draft, avatar_asset_id: null, avatar_url: null });
            }}
          >
            {t("profileRemoveAvatar")}
          </Button>
        ) : null}
        {error ? (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        ) : null}
        <div className="border-border flex flex-col-reverse gap-2 border-t pt-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setEditing(false);
              setDraft(initial);
              setPreview(false);
              setError(null);
              receipt.current = null;
            }}
          >
            {c("cancel")}
          </Button>
          <Button type="submit" disabled={!draft.name.trim()}>
            {pending ? c("loading") : t("profileSave")}
          </Button>
        </div>
      </fieldset>
    </form>
  );
}
