"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { unlinkIdentityAction } from "@/actions/account";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import type { LinkedIdentity } from "@/lib/api/generated/types.gen";

const ALL_PROVIDERS = ["google", "github"] as const;

type IdentityListProps = {
  identities: LinkedIdentity[];
  csrfToken: string;
  /** Relative path returned after step-up OAuth (e.g. /en/account). */
  returnTo: string;
};

function providerLabel(provider: string, t: (key: string) => string): string {
  if (provider === "google") {
    return t("providerGoogle");
  }
  if (provider === "github") {
    return t("providerGithub");
  }
  return provider;
}

function linkHref(provider: "google" | "github", returnTo: string): string {
  const params = new URLSearchParams({ return_to: returnTo });
  // Browser navigates via Caddy so the OAuth handshake cookie is set client-side.
  return `/v1/auth/link/${provider}?${params.toString()}`;
}

export function IdentityList({ identities, csrfToken, returnTo }: IdentityListProps) {
  const t = useTranslations("account");
  const tc = useTranslations("common");
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busyProvider, setBusyProvider] = useState<string | null>(null);

  const linked = new Set(identities.map((item) => item.provider));
  const canUnlink = identities.length > 1;
  const missing = ALL_PROVIDERS.filter((provider) => !linked.has(provider));

  function onUnlink(provider: "google" | "github") {
    if (!canUnlink) {
      toast.error(t("unlinkLastBlocked"));
      return;
    }
    setBusyProvider(provider);
    startTransition(() => {
      void (async () => {
        const result = await unlinkIdentityAction({ provider, csrfToken });
        setBusyProvider(null);
        if (!result.ok) {
          toast.error(result.message || t("unlinkFailed"));
          return;
        }
        toast.success(t("unlinked"));
        router.refresh();
      })();
    });
  }

  return (
    <div className="space-y-4">
      <ul className="space-y-3">
        {identities.map((identity) => {
          const provider = identity.provider;
          const avatar = typeof identity.avatar_url === "string" ? identity.avatar_url : null;
          const displayName =
            typeof identity.display_name === "string" ? identity.display_name : null;
          const isBusy = pending && busyProvider === provider;
          return (
            <li
              key={`${provider}-${identity.linked_at}`}
              className="border-border bg-card text-card-foreground flex flex-wrap items-center gap-3 rounded-lg border p-3 shadow-sm"
            >
              {avatar ? (
                <img
                  src={avatar}
                  alt=""
                  width={40}
                  height={40}
                  className="border-border h-10 w-10 rounded-full border object-cover"
                  referrerPolicy="no-referrer"
                />
              ) : (
                <div
                  className="bg-muted text-muted-foreground flex h-10 w-10 items-center justify-center rounded-full font-mono text-sm font-medium uppercase"
                  aria-hidden
                >
                  {provider.slice(0, 1)}
                </div>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{providerLabel(provider, t)}</Badge>
                  {displayName ? (
                    <span className="truncate text-sm font-medium">{displayName}</span>
                  ) : null}
                </div>
                <p className="text-muted-foreground mt-0.5 font-mono text-[11px]">
                  {t("availableForSignIn")}
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!canUnlink || pending}
                onClick={() => {
                  onUnlink(provider);
                }}
              >
                {isBusy ? tc("loading") : t("unlink")}
              </Button>
            </li>
          );
        })}
      </ul>
      {!canUnlink ? <p className="text-muted-foreground text-xs">{t("unlinkLastHint")}</p> : null}
      {missing.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">{t("linkAnother")}</h3>
          <div className="flex flex-wrap gap-2">
            {missing.map((provider) => (
              <Button key={provider} asChild size="sm" variant="secondary">
                <a href={linkHref(provider, returnTo)}>{providerLabel(provider, t)}</a>
              </Button>
            ))}
          </div>
          <p className="text-muted-foreground text-xs">{t("linkAnotherHint")}</p>
        </div>
      ) : null}
    </div>
  );
}
