"use client";

import { useRef } from "react";
import type { useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import { Icon } from "@/theme/icons";
import { Link } from "@/lib/i18n/navigation";
import type { OwnerPublicProfile, ProfileLink } from "@/lib/api/public-profile";
import { renderMarkdownOnServer } from "@/lib/markdown/render";
import { PROFILE_BIO_MAX, useProfileForm } from "@/components/organisms/use-profile-form";

type ProfileFormProps = {
  initial: OwnerPublicProfile;
  sessionToken: string;
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

function LinksEditor(props: {
  links: ProfileLink[];
  t: TAccount;
  onChange: (links: ProfileLink[]) => void;
}) {
  const { links, t, onChange } = props;
  return (
    <section className="space-y-3">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-medium">{t("profileLinks")}</h2>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 sm:min-h-8"
          onClick={() => {
            onChange([...links, { label: "", url: "https://" }]);
          }}
          disabled={links.length >= 8}
        >
          {t("profileAddLink")}
        </Button>
      </div>
      {links.length === 0 ? (
        <p className="text-muted-foreground text-xs">{t("profileLinksEmpty")}</p>
      ) : null}
      {links.map((link, index) => (
        <div key={index} className="grid min-w-0 items-end gap-2 sm:grid-cols-[1fr_2fr_auto]">
          <div className="space-y-1.5">
            <Label htmlFor={`profile-link-label-${index}`}>{t("linkLabel")}</Label>
            <Input
              id={`profile-link-label-${index}`}
              value={link.label}
              maxLength={60}
              onChange={(e) => {
                onChange(
                  links.map((item, i) => (i === index ? { ...item, label: e.target.value } : item)),
                );
              }}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`profile-link-url-${index}`}>{t("linkUrl")}</Label>
            <Input
              id={`profile-link-url-${index}`}
              className="font-mono"
              value={link.url}
              placeholder="https://"
              onChange={(e) => {
                onChange(
                  links.map((item, i) => (i === index ? { ...item, url: e.target.value } : item)),
                );
              }}
            />
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="min-h-11 w-full sm:min-h-8 sm:w-auto"
            onClick={() => {
              onChange(links.filter((_, i) => i !== index));
            }}
          >
            {t("profileRemoveLink")}
          </Button>
        </div>
      ))}
    </section>
  );
}

function BioEditor(props: {
  bio: string;
  mode: "plain" | "render";
  error: string | null;
  t: TAccount;
  onBio: (value: string) => void;
  onMode: (mode: "plain" | "render") => void;
}) {
  const { bio, mode, error, t, onBio, onMode } = props;
  const rendered = mode === "render" ? renderMarkdownOnServer(bio || "") : null;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label htmlFor="profile-bio">{t("profileBio")}</Label>
        <div
          className="border-border bg-muted/40 inline-flex rounded-sm border p-0.5"
          role="group"
          aria-label={t("profileBioMode")}
        >
          <Button
            type="button"
            size="sm"
            variant={mode === "plain" ? "secondary" : "ghost"}
            className="h-7 px-2.5 text-xs"
            onClick={() => {
              onMode("plain");
            }}
          >
            {t("profileBioPlain")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant={mode === "render" ? "secondary" : "ghost"}
            className="h-7 px-2.5 text-xs"
            onClick={() => {
              onMode("render");
            }}
          >
            {t("profileBioRender")}
          </Button>
        </div>
      </div>
      {mode === "plain" ? (
        <Textarea
          id="profile-bio"
          className="min-h-28 font-mono"
          value={bio}
          onChange={(e) => {
            onBio(e.target.value);
          }}
          maxLength={PROFILE_BIO_MAX}
          aria-label={t("profileBio")}
        />
      ) : (
        <div
          className="border-input bg-background prose-sm min-h-28 w-full overflow-x-auto rounded-sm border px-3 py-2 text-sm leading-relaxed [&_a]:underline [&_code]:font-mono [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:pl-5"
          dangerouslySetInnerHTML={{
            __html:
              rendered?.html || `<p class="text-muted-foreground">${t("profileBioEmpty")}</p>`,
          }}
        />
      )}
      <p className="text-muted-foreground font-mono text-xs">
        {t("profileBioHint")} · {bio.length}/{PROFILE_BIO_MAX}
      </p>
      {error ? <p className="text-destructive text-xs">{error}</p> : null}
    </div>
  );
}

/**
 * Public profile editor. Preview stays browser-only; save and publish remain explicit actions.
 */
export function ProfileForm({ initial, sessionToken }: ProfileFormProps) {
  const form = useProfileForm(initial, sessionToken);
  const statusVariant =
    form.status === "published" ? "success" : form.status === "draft" ? "warning" : "outline";
  const statusLabel =
    form.status === "published"
      ? form.t("profileStatusPublished")
      : form.status === "draft"
        ? form.t("profileStatusDraft")
        : form.t("profileStatusEmpty");

  return (
    <div className="border-border bg-card min-w-0 space-y-6 rounded-lg border p-5 shadow-sm sm:p-6">
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

      <AvatarControls
        avatarUrl={form.shownAvatar}
        pending={form.pending}
        t={form.t}
        onFile={form.onFile}
        onImport={form.onImport}
        onRemove={form.onRemoveAvatar}
      />

      <div className="space-y-2">
        <Label htmlFor="profile-display-name">{form.t("profileDisplayName")}</Label>
        <Input
          id="profile-display-name"
          value={form.displayName}
          onChange={(e) => {
            form.setDisplayName(e.target.value);
          }}
          maxLength={80}
          autoComplete="nickname"
        />
      </div>

      <BioEditor
        bio={form.bio}
        mode={form.bioMode}
        error={form.bioError}
        t={form.t}
        onBio={form.setBio}
        onMode={form.setBioMode}
      />

      <LinksEditor links={form.links} t={form.t} onChange={form.setLinks} />

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
    </div>
  );
}
