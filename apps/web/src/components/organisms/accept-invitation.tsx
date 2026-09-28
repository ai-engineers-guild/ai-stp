"use client";

import { useEffect, useRef, useState, useSyncExternalStore, useTransition } from "react";

import { Button } from "@/components/atoms/button";
import { MutationReference } from "@/components/molecules/mutation-reference";
import { useHydrated } from "@/lib/use-hydrated";
import { CSRF_COOKIE } from "@/lib/auth/cookies";

type AcceptInvitationProps = {
  invitationId: string;
  /** Same-origin accept endpoint; defaults to the grant invitation hop. */
  endpoint?: string;
  /**
   * Where an unauthenticated accept click is sent to sign in. The current
   * path plus the still-held fragment becomes `returnTo`, so the bearer token
   * survives the OAuth round trip in the browser only.
   */
  signInHref?: string;
  /**
   * Where a signed-in but not-yet-onboarded account is sent. Same `returnTo`
   * fragment carry as `signInHref`; onboarding redirects back when done.
   */
  onboardingHref?: string;
  labels: {
    accept: string;
    accepting: string;
    missingToken: string;
    success: string;
    error: string;
    referenceId: string;
  };
};

function readCsrfFromDocument(): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const match = document.cookie.split("; ").find((row) => row.startsWith(`${CSRF_COOKIE}=`));
  if (!match) {
    return null;
  }
  return decodeURIComponent(match.slice(CSRF_COOKIE.length + 1));
}

function readFragmentToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  if (!raw) {
    return null;
  }
  const params = new URLSearchParams(raw);
  const token = params.get("token");
  return token && token.length > 0 ? token : null;
}

function scrubFragment(): void {
  if (typeof window === "undefined") {
    return;
  }
  const { pathname, search } = window.location;
  window.history.replaceState(null, "", `${pathname}${search}`);
}

/**
 * Fragment-only invitation accept (REQ-2714 / ADR-0047).
 * Token lives in memory; never Server Action / RSC / storage / logs.
 */
export function AcceptInvitation({
  invitationId,
  endpoint,
  signInHref,
  onboardingHref,
  labels,
}: AcceptInvitationProps) {
  // The token lives in the URL fragment, which the server never sees. Reading
  // it during render and scrubbing it in an effect separates the question from
  // the side effect; setting both from one effect cost a render pass and made
  // `ready` a second name for "hydrated".
  const fragmentToken = useSyncExternalStore(
    () => () => {},
    readFragmentToken,
    () => null,
  );
  const ready = useHydrated();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [operationId, setOperationId] = useState<string | null>(null);
  const [consumed, setConsumed] = useState(false);
  // Once consumed, the token is gone for this mount whatever the fragment
  // still says. Scrubbing removes it from the URL as well, but the flag is
  // what makes a remount unable to re-use it.
  const token = consumed ? null : fragmentToken;
  // The scrubbed fragment is kept in memory so a sign-in redirect can rebuild
  // it into `returnTo` — the login round trip loses the URL hash otherwise.
  // Ref, not state: the value must not be rendered and must not re-render.
  const heldFragment = useRef<string | null>(null);

  useEffect(() => {
    if (fragmentToken) {
      if (heldFragment.current === null) {
        heldFragment.current = window.location.hash;
      }
      scrubFragment();
    }
  }, [fragmentToken]);

  if (!ready) {
    return null;
  }

  if (success) {
    return (
      <div className="space-y-3">
        <p className="text-sm" role="status">
          {labels.success}
        </p>
        <MutationReference label={labels.referenceId} operationId={operationId} />
      </div>
    );
  }

  if (!token && !consumed) {
    return (
      <p className="text-muted-foreground text-sm" role="status">
        {labels.missingToken}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {token ? (
        <Button
          type="button"
          disabled={pending}
          onClick={() => {
            setError(null);
            startTransition(async () => {
              const held = token;
              // Marked consumed immediately so remounts cannot re-use it.
              setConsumed(true);
              const redirectToAuth = (target: string) => {
                const { pathname, search } = window.location;
                const returnTo = `${pathname}${search}${heldFragment.current ?? ""}`;
                window.location.assign(`${target}?${new URLSearchParams({ returnTo }).toString()}`);
              };
              try {
                const csrf = readCsrfFromDocument();
                if (!held) {
                  setError(labels.error);
                  return;
                }
                // The CSRF cookie is minted with the session at login — its
                // absence means this browser is not signed in. Send them to
                // sign in rather than failing on a request that cannot pass
                // the route's CSRF check anyway.
                if (!csrf) {
                  if (signInHref) {
                    redirectToAuth(signInHref);
                  } else {
                    setError(labels.error);
                  }
                  return;
                }
                const idempotencyKey = crypto.randomUUID().replaceAll("-", "");
                const response = await fetch(
                  endpoint ?? `/api/grants/invitations/${encodeURIComponent(invitationId)}/accept`,
                  {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                      Accept: "application/json",
                      "Content-Type": "application/json",
                      "X-CSRF-Token": csrf,
                    },
                    body: JSON.stringify({
                      token: held,
                      idempotency_key: idempotencyKey,
                    }),
                  },
                );
                let redirectTarget: string | null = null;
                if (response.status === 401 && signInHref) {
                  redirectTarget = signInHref;
                } else if (response.status === 409 && onboardingHref) {
                  // The API also uses 409 for replayed/revoked invitations —
                  // only the route's own code means "go finish onboarding".
                  const data = (await response.json().catch(() => null)) as {
                    error?: { code?: string };
                  } | null;
                  if (data?.error?.code === "AI_STP_ONBOARDING_REQUIRED") {
                    redirectTarget = onboardingHref;
                  }
                }
                if (redirectTarget) {
                  redirectToAuth(redirectTarget);
                  return;
                }
                if (!response.ok) {
                  setError(labels.error);
                  return;
                }
                setSuccess(true);
                setOperationId(response.headers.get("x-operation-id"));
              } catch {
                setError(labels.error);
              }
            });
          }}
        >
          {pending ? labels.accepting : labels.accept}
        </Button>
      ) : null}
      {error ? (
        <p className="text-destructive text-sm" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
