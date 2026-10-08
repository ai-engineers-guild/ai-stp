"use client";

import { useRef } from "react";
import type { useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import {
  EntityEditorErrorSummary,
  EntityEditorField,
  EntityEditorLayout,
  EntityEditorSection,
} from "@/components/molecules/entity-editor-layout";
import { EntityLinksEditor } from "@/components/molecules/entity-links-editor";
import { MarkdownEditor } from "@/components/molecules/markdown-editor";
import { Icon } from "@/theme/icons";
import { Link } from "@/lib/i18n/navigation";
import type { OwnerPublicProfile } from "@/lib/api/public-profile";
import { ENTITY_EDITOR_CONFIGS } from "@/lib/entity-editor-contract";
import { PROFILE_BIO_MAX, useProfileForm } from "@/lib/use-profile-form";

type ProfileFormProps = {
  initial: OwnerPublicProfile;
  csrfToken: string;
};

type TAccount = ReturnType<typeof useTranslations<"account">>;

function AvatarControls(props: {
  avatarUrl: string | null;
  pending: boolean;
  t: TAccount;
  onFile: (file: File | null) => void;
  onImport: (provider: "github" | "google") => void;
  onRemove: () => void;
  error?: string | undefined;
}) {
  const { avatarUrl, pending, t, onFile, onImport, onRemove, error } = props;
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <section className="flex min-w-0 flex-col items-start gap-4 sm:flex-row sm:flex-wrap">
      <button
        type="button"
        className={`group bg-muted border-border focus-visible:ring-ring hover:border-foreground/40 relative flex h-20 w-20 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-full border transition-[border-color,box-shadow] hover:shadow-sm focus-visible:ring-2 focus-visible:outline-none disabled:cursor-wait ${error ? "border-destructive focus-visible:ring-destructive" : ""}`}
        onClick={() => inputRef.current?.click()}
        disabled={pending}
        aria-label={t("profileUpload")}
        aria-describedby={error ? "profile-avatar-error" : undefined}
      >
        {avatarUrl ? (
          <img src={avatarUrl} alt="" className="h-20 w-20 object-cover" />
        ) : (
          <Icon name="user" size="lg" className="text-muted-foreground" />
        )}
        <span className="bg-foreground/72 text-background absolute inset-0 flex items-center justify-center opacity-0 backdrop-blur-[1px] transition-opacity duration-200 group-hover:opacity-100 group-focus-visible:opacity-100">
          <Icon
            name={pending ? "loader" : "camera"}
            size="md"
            className={pending ? "animate-spin" : ""}
          />
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="sr-only"
        aria-invalid={Boolean(error)}
        aria-describedby={error ? "profile-avatar-error" : undefined}
        onChange={(e) => {
          onFile(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />
      <div className="min-w-0 flex-1 space-y-2 pt-0.5">
        <p className="text-muted-foreground max-w-md text-xs leading-relaxed">
          {t("profileAvatarRequirements")}
        </p>
        <p className="text-muted-foreground text-xs font-medium">{t("profileIdentitySources")}</p>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={pending}
            onClick={() => {
              onImport("github");
            }}
          >
            <Icon name="github" size="sm" />
            {t("profileImportGithub")}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={pending}
            onClick={() => {
              onImport("google");
            }}
          >
            <Icon name="google" size="sm" />
            {t("profileImportGoogle")}
          </Button>
          {avatarUrl ? (
            <Button type="button" variant="outline" size="sm" disabled={pending} onClick={onRemove}>
              {t("profileRemoveAvatar")}
            </Button>
          ) : null}
        </div>
        {error ? (
          <p id="profile-avatar-error" className="text-destructive text-xs" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}

/**
 * Public profile editor. Preview stays browser-only; save and publish remain explicit actions.
 */
// eslint-disable-next-line max-lines-per-function -- profile editor composes the shared layout blocks and footer.
export function ProfileForm({ initial, csrfToken }: ProfileFormProps) {
  const form = useProfileForm(initial, csrfToken);
  const statusVariant =
    form.status === "published" ? "success" : form.status === "draft" ? "warning" : "outline";
  const statusLabel =
    form.status === "published"
      ? form.t("profileStatusPublished")
      : form.status === "draft"
        ? form.t("profileStatusDraft")
        : form.t("profileStatusEmpty");

  return (
    <EntityEditorLayout
      hydrationReady={form.storageReady}
      config={ENTITY_EDITOR_CONFIGS.profile}
      title={form.t("profile")}
      description={form.t("profileSubtitle")}
      beforeBlocks={
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
          <div className="space-y-1">
            <Badge variant={statusVariant}>{statusLabel}</Badge>
            <p className="text-muted-foreground text-xs">{form.t("profileStatusHint")}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {initial.published ? (
              <Button asChild variant="ghost" size="sm">
                <Link href={`/publishers/${initial.account_id}`} prefetch={false}>
                  {form.t("viewPublicProfile")}
                </Link>
              </Button>
            ) : null}
            <Button asChild variant="outline" size="sm">
              <Link
                href="/account/profile/preview"
                prefetch={false}
                onClick={(event) => {
                  event.preventDefault();
                  form.persistPreview();
                  window.location.assign(event.currentTarget.href);
                }}
              >
                {form.t("profilePreview")}
              </Link>
            </Button>
          </div>
        </div>
      }
      blocks={{
        avatar: (
          <EntityEditorSection title={form.t("profileUpload")}>
            <AvatarControls
              avatarUrl={form.shownAvatar}
              pending={form.pending}
              t={form.t}
              onFile={form.onFile}
              onImport={form.onImport}
              onRemove={form.onRemoveAvatar}
              error={form.fieldErrors.avatar}
            />
          </EntityEditorSection>
        ),
        displayName: (
          <EntityEditorField
            label={form.t("profileDisplayName")}
            htmlFor="profile-display-name"
            required
            error={form.fieldErrors.display_name}
          >
            <Input
              id="profile-display-name"
              value={form.displayName}
              onChange={(e) => {
                form.setDisplayName(e.target.value);
              }}
              maxLength={80}
              className={
                form.fieldErrors.display_name
                  ? "border-destructive focus-visible:ring-destructive"
                  : undefined
              }
              aria-invalid={Boolean(form.fieldErrors.display_name)}
              aria-describedby={
                form.fieldErrors.display_name ? "profile-display-name-error" : undefined
              }
              autoComplete="nickname"
            />
          </EntityEditorField>
        ),
        description: (
          <MarkdownEditor
            id="profile-bio"
            label={form.t("profileBio")}
            value={form.bio}
            mode={form.bioMode === "plain" ? "write" : "preview"}
            onChange={form.setBio}
            onModeChange={(mode) => {
              form.setBioMode(mode === "write" ? "plain" : "render");
            }}
            maxLength={PROFILE_BIO_MAX}
            hint={form.t("profileBioHint")}
            error={form.bioError}
            labels={{ write: form.t("profileBioPlain"), preview: form.t("profileBioRender") }}
          />
        ),
        links: (
          <EntityLinksEditor
            links={form.links}
            max={ENTITY_EDITOR_CONFIGS.profile.limits.links}
            labels={{
              title: form.t("profileLinks"),
              add: form.t("profileAddLink"),
              empty: form.t("profileLinksEmpty"),
              label: form.t("linkLabel"),
              url: form.t("linkUrl"),
              remove: form.t("profileRemoveLink"),
            }}
            onChange={form.setLinks}
            disabled={form.pending}
            fieldErrors={form.fieldErrors}
            idPrefix="profile-link"
          />
        ),
      }}
      afterBlocks={
        <>
          <EntityEditorErrorSummary
            error={form.error}
            fieldErrors={form.fieldErrors}
            summary={form.t("profileErrorFieldSummary")}
            fieldLabel={(path) => profileFieldLabel(path, form.t)}
          />
          {form.message ? (
            <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
              {form.message}
            </p>
          ) : null}

          <div className="border-border flex flex-col gap-3 border-t pt-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
            <div className="max-w-sm space-y-1">
              <p className="text-muted-foreground text-xs">{form.t("profilePreviewHint")}</p>
              {form.canRestorePublished ? (
                <button
                  type="button"
                  className="min-h-11 text-xs underline underline-offset-4 sm:min-h-0"
                  onClick={form.restorePublished}
                  disabled={form.pending}
                >
                  {form.t("profileRestorePublished")}
                </button>
              ) : null}
            </div>
            <div className="flex w-full flex-col-reverse gap-2 sm:w-auto sm:flex-row">
              <Button
                type="button"
                variant="secondary"
                className="min-h-11 w-full sm:w-auto"
                disabled={form.pending || Boolean(form.bioError)}
                onClick={form.saveDraft}
              >
                {form.t("profileSave")}
              </Button>
              <Button
                type="button"
                className="min-h-11 w-full sm:w-auto"
                disabled={form.pending || Boolean(form.bioError)}
                onClick={form.publish}
              >
                {form.t("profilePublish")}
              </Button>
            </div>
          </div>
        </>
      }
    />
  );
}

function profileFieldLabel(path: string, t: TAccount): string {
  if (path === "display_name" || path === "name") return t("profileDisplayName");
  if (path === "bio") return t("profileBio");
  if (path === "avatar") return t("profileUpload");
  const match = path.match(/^links\.(\d+)\.(label|url)$/);
  if (match)
    return `${t("profileLinks")} #${Number(match[1]) + 1} ${match[2] === "label" ? t("linkLabel") : t("linkUrl")}`;
  return path;
}
