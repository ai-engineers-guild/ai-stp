"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { unlinkIdentityAction } from "@/actions/account";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import type { LinkedIdentity, OAuthProvider } from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";

type IdentityListProps = {
  identities: LinkedIdentity[];
  csrfToken: string;
  /** Relative path returned after step-up OAuth (e.g. /en/account). */
  returnTo: string;
  /** Sign-in providers enabled for this deployment (env.AI_STP_AUTH_PROVIDERS). */
  providers: readonly OAuthProvider[];
};

function providerLabel(provider: string, t: (key: string) => string): string {
  if (provider === "google") {
    return t("providerGoogle");
  }
  if (provider === "github") {
    return t("providerGithub");
  }
  if (provider === "authentik") {
    return t("providerAuthentik");
  }
  if (provider === "keycloak") {
    return t("providerKeycloak");
  }
  if (provider === "gitlab") {
    return t("providerGitlab");
  }
  if (provider === "saml") {
    return t("providerSaml");
  }
  return provider;
}

function linkHref(provider: OAuthProvider, returnTo: string): string {
  const params = new URLSearchParams({ return_to: returnTo });
  // Browser navigates via the edge proxy so the OAuth handshake cookie is set client-side.
  return `/v1/auth/link/${provider}?${params.toString()}`;
}

function providerIcon(provider: string): "google" | "github" | "gitlab" | "user" {
  if (provider === "google") return "google";
  if (provider === "github") return "github";
  if (provider === "gitlab") return "gitlab";
  return "user";
}

export function IdentityList({ identities, csrfToken, returnTo, providers }: IdentityListProps) {
  const t = useTranslations("account");
  const tc = useTranslations("common");
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busyProvider, setBusyProvider] = useState<string | null>(null);

  const linked = new Set(identities.map((item) => item.provider));
  const canUnlink = identities.length > 1;
  const missing = providers.filter((provider) => !linked.has(provider));

  function onUnlink(provider: OAuthProvider) {
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
              className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-background p-3 text-card-foreground sm:p-4"
            >
              <div className="grid size-11 shrink-0 place-items-center rounded-full bg-muted text-foreground">
                {avatar ? (
                  // biome-ignore lint/performance/noImgElement: Browser previews and account-provided asset URLs must not be fetched by an image proxy.
                  <img
                    src={avatar}
                    alt=""
                    width={44}
                    height={44}
                    className="size-11 rounded-full border border-border object-cover"
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <Icon name={providerIcon(provider)} size="md" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{providerLabel(provider, t)}</Badge>
                  {displayName ? (
                    <span className="truncate text-sm font-medium">{displayName}</span>
                  ) : null}
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">{t("availableForSignIn")}</p>
              </div>
              <span className="inline-flex items-center gap-2 text-sm text-success">
                <span aria-hidden="true" className="size-2 rounded-full bg-success" />
                <span>{t("connected")}</span>
              </span>
              <Button
                type="button"
                variant="outline"
                className="min-h-11 shrink-0"
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
      {!canUnlink ? <p className="text-xs text-muted-foreground">{t("unlinkLastHint")}</p> : null}
      {missing.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">{t("linkAnother")}</h3>
          <div className="flex flex-wrap gap-2">
            {missing.map((provider) => (
              <Button key={provider} asChild variant="outline" className="min-h-11">
                <a href={linkHref(provider, returnTo)}>{providerLabel(provider, t)}</a>
              </Button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">{t("linkAnotherHint")}</p>
        </div>
      ) : null}
    </div>
  );
}
