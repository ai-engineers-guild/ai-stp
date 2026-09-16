"use client";

import { useRef } from "react";
import type { useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import {
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
import { PROFILE_BIO_MAX, useProfileForm } from "@/components/organisms/use-profile-form";

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
}) {
  const { avatarUrl, pending, t, onFile, onImport, onRemove } = props;
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <section className="flex min-w-0 flex-col items-start gap-4 sm:flex-row sm:flex-wrap">
      <button
        type="button"
        className="group bg-muted border-border focus-visible:ring-ring hover:border-foreground/40 relative flex h-20 w-20 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-full border transition-[border-color,box-shadow] hover:shadow-sm focus-visible:ring-2 focus-visible:outline-none disabled:cursor-wait"
        onClick={() => inputRef.current?.click()}
        disabled={pending}
        aria-label={t("profileUpload")}
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
            <GitHubMark />
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
            <GoogleMark />
            {t("profileImportGoogle")}
          </Button>
          {avatarUrl ? (
            <Button type="button" variant="outline" size="sm" disabled={pending} onClick={onRemove}>
              {t("profileRemoveAvatar")}
            </Button>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function GitHubMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-3.5 fill-current">
      <path d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.87c-2.78.6-3.37-1.18-3.37-1.18-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.61.07-.61 1 .07 1.53 1.03 1.53 1.03.9 1.53 2.35 1.09 2.92.83.09-.65.35-1.09.64-1.34-2.22-.25-4.55-1.11-4.55-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02A9.6 9.6 0 0 1 12 6.82a9.6 9.6 0 0 1 2.5.34c1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.69-4.57 4.94.36.31.68.92.68 1.85v2.75c0 .27.18.58.69.48A10 10 0 0 0 12 2Z" />
    </svg>
  );
}

function GoogleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-3.5">
      <path
        fill="currentColor"
        d="M21.6 12.23c0-.71-.06-1.4-.18-2.07H12v3.91h5.38a4.6 4.6 0 0 1-2 3.02v2.54h3.24c1.9-1.75 2.98-4.33 2.98-7.4Z"
      />
      <path
        fill="currentColor"
        d="M12 22c2.7 0 4.97-.9 6.62-2.43l-3.24-2.54c-.9.6-2.05.96-3.38.96-2.61 0-4.82-1.76-5.61-4.13H3.04v2.62A10 10 0 0 0 12 22Z"
      />
      <path
        fill="currentColor"
        d="M6.39 13.86A6 6 0 0 1 6.08 12c0-.65.11-1.28.31-1.86V7.52H3.04A10 10 0 0 0 2 12c0 1.61.38 3.14 1.04 4.48l3.35-2.62Z"
      />
      <path
        fill="currentColor"
        d="M12 6.01c1.47 0 2.79.51 3.83 1.5l2.87-2.87A9.63 9.63 0 0 0 12 2a10 10 0 0 0-8.96 5.52l3.35 2.62C7.18 7.77 9.39 6.01 12 6.01Z"
      />
    </svg>
  );
}

/**
 * Public profile editor. Preview stays browser-only; save and publish remain explicit actions.
 */
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
            />
          </EntityEditorSection>
        ),
        displayName: (
          <EntityEditorField
            label={form.t("profileDisplayName")}
            htmlFor="profile-display-name"
            required
          >
            <Input
              id="profile-display-name"
              value={form.displayName}
              onChange={(e) => {
                form.setDisplayName(e.target.value);
              }}
              maxLength={80}
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
            idPrefix="profile-link"
          />
        ),
      }}
      afterBlocks={
        <>
          {form.error ? (
            <p className="text-destructive text-sm" role="alert">
              {form.error}
            </p>
          ) : null}
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
