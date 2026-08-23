"use client";

import { useMemo, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/atoms/button";
import {
  PROFILE_PREVIEW_STORAGE_KEY,
  readLocalProfilePreview,
} from "@/lib/profile-preview-storage";
import { Icon } from "@/theme/icons";
import type { PublicProfileProjection } from "@/lib/api/public-profile";
import { renderMarkdownOnServer } from "@/lib/markdown/render";

type ProfilePreviewProps = {
  projection: PublicProfileProjection;
  copyLabel: string;
  copiedLabel: string;
};

/** Renders the current browser-only form state without creating a backend draft. */
export function ProfilePreview({ projection, copyLabel, copiedLabel }: ProfilePreviewProps) {
  const [copied, setCopied] = useState(false);
  // Session storage is an external store, so it is read during render rather
  // than copied into state by an effect. The snapshot is the raw string:
  // `useSyncExternalStore` compares by identity, and returning a freshly
  // parsed object every call would never settle.
  const stored = useSyncExternalStore(
    () => () => {},
    () => {
      try {
        return window.sessionStorage.getItem(PROFILE_PREVIEW_STORAGE_KEY);
      } catch {
        // Server projection remains the safe fallback when storage is refused.
        return null;
      }
    },
    () => null,
  );
  const local = useMemo(
    () => (stored === null ? null : readLocalProfilePreview(projection.account_id)),
    [stored, projection.account_id],
  );

  const displayName = local?.displayName.trim() || projection.display_name || projection.account_id;
  const bio = local?.bio ?? projection.bio;
  const links = local?.links ?? projection.links;
  const avatarUrl = local?.avatarUrl ?? projection.avatar_url;
  const bioHtml = bio ? renderMarkdownOnServer(bio).html : null;

  async function copyAccountId() {
    await navigator.clipboard.writeText(projection.account_id);
    setCopied(true);
    window.setTimeout(() => {
      setCopied(false);
    }, 1400);
  }

  return (
    <section className="flex flex-wrap items-start gap-5">
      <div className="bg-muted border-border flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-full border text-sm font-medium">
        {avatarUrl ? (
          <img src={avatarUrl} alt="" className="h-20 w-20 rounded-full object-cover" />
        ) : (
          displayName.slice(0, 2).toUpperCase()
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h1 className="text-3xl font-medium tracking-tight">{displayName}</h1>
          <Button type="button" variant="outline" size="sm" onClick={() => void copyAccountId()}>
            <Icon name={copied ? "check" : "copy"} size="sm" />
            {copied ? copiedLabel : copyLabel}
          </Button>
        </div>
        {links.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {links.map((link) => (
              <li key={link.url}>
                <a
                  href={link.url}
                  className="border-border bg-card hover:bg-muted inline-flex max-w-full items-center rounded-md border px-3 py-1.5 text-sm font-medium no-underline transition-colors"
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  <span className="truncate">{link.label}</span>
                </a>
              </li>
            ))}
          </ul>
        ) : null}
        {bioHtml ? (
          <div
            className="prose-sm text-muted-foreground max-w-prose overflow-x-auto text-sm leading-relaxed [&_a]:underline [&_a]:underline-offset-2 [&_code]:font-mono [&_ol]:list-decimal [&_ol]:pl-5 [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:p-2 [&_th]:border [&_th]:p-2 [&_ul]:list-disc [&_ul]:pl-5"
            dangerouslySetInnerHTML={{ __html: bioHtml }}
          />
        ) : null}
      </div>
    </section>
  );
}
