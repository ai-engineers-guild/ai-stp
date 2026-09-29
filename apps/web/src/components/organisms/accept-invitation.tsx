"use client";

import { useEffect, useRef, useState, useSyncExternalStore, useTransition } from "react";

import { Button } from "@/components/atoms/button";
import { MutationReference } from "@/components/molecules/mutation-reference";
import { useHydrated } from "@/lib/use-hydrated";
import {
  CSRF_COOKIE,
  hasInvitationClaimFlag,
  type InvitationClaimVariant,
} from "@/lib/auth/cookies";

type AcceptInvitationProps = {
  invitationId: string;
  /** Same-origin accept endpoint; defaults to the grant invitation hop. */
  endpoint?: string;
  /**
   * Same-origin claim parking endpoint (corporate invitations only). On
   * fragment read the token is POSTed there once and parked in an httpOnly
   * cookie — it survives reloads and the login round trip without ever being
   * JS-readable again.
   */
  holdEndpoint?: string;
  /** Which claim cookie pair the hold/accept hops use. */
  holdVariant?: InvitationClaimVariant;
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
    /** Shown when the API mails a confirmation to the invited address. */
    confirmationSent?: string;
    /** Resend affordance on that state; hidden when unset. */
    resendConfirmation?: string;
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

// Per-path snapshot of the fragment the page was opened with. The store's
// getSnapshot is re-read on every render while the scrub effect deletes the
// hash right after mount — without the memo every StrictMode remount or state
// update would collapse the token to null and show "no token in this tab" on
// a link that was just opened. A live hash always wins over the memo, so a
// second emailed link still takes over.
const fragmentSnapshots = new Map<string, string | null>();

function readFragmentToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  const live = raw ? new URLSearchParams(raw).get("token") : null;
  if (live && live.length > 0) {
    fragmentSnapshots.set(window.location.pathname, live);
    return live;
  }
  return fragmentSnapshots.get(window.location.pathname) ?? null;
}

function scrubFragment(): void {
  if (typeof window === "undefined") {
    return;
  }
  const { pathname, search } = window.location;
  window.history.replaceState(null, "", `${pathname}${search}`);
}

/**
 * Park the fragment token in an httpOnly cookie via the hold route so a
 * reload or the login round trip cannot lose it. Anonymous visits have no
 * CSRF cookie — the route answers 403, the `returnTo` fragment still covers
 * that leg, and the post-login mount retries the hold.
 */
function useClaimParking(
  fragmentToken: string | null,
  holdEndpoint: string | undefined,
  holdVariant: InvitationClaimVariant | undefined,
): void {
  useEffect(() => {
    if (!fragmentToken || !holdEndpoint || !holdVariant) {
      return;
    }
    const csrf = readCsrfFromDocument();
    void fetch(holdEndpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      },
      body: JSON.stringify({ token: fragmentToken, variant: holdVariant }),
    }).catch(() => undefined);
  }, [fragmentToken, holdEndpoint, holdVariant]);
}

type SubmitOutcome =
  | { kind: "success"; operationId: string | null }
  | { kind: "confirmation_sent" }
  | { kind: "unauthorized" }
  | { kind: "onboarding" }
  | { kind: "error" };

/**
 * POST the held token to the same-origin hop and classify the answer. The
 * route treats a missing body token as "use the parked claim cookie", so
 * `held` may be null on fragment-less revisits.
 */
async function postAcceptance(
  endpoint: string | undefined,
  invitationId: string,
  held: string | null,
  csrf: string,
): Promise<SubmitOutcome> {
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
        // Omitted (not null) when the parked cookie should speak.
        ...(held === null ? {} : { token: held }),
        idempotency_key: crypto.randomUUID().replaceAll("-", ""),
      }),
    },
  );
  if (response.status === 401) {
    return { kind: "unauthorized" };
  }
  if (response.status === 409) {
    // The API also uses 409 for replayed/revoked invitations — only the
    // route's own codes mean "go finish onboarding" or "check the mail".
    const data = (await response.json().catch(() => null)) as {
      error?: { code?: string };
    } | null;
    if (data?.error?.code === "AI_STP_ONBOARDING_REQUIRED") {
      return { kind: "onboarding" };
    }
    if (data?.error?.code === "AI_STP_EMAIL_CONFIRMATION_SENT") {
      return { kind: "confirmation_sent" };
    }
    return { kind: "error" };
  }
  if (!response.ok) {
    return { kind: "error" };
  }
  return { kind: "success", operationId: response.headers.get("x-operation-id") };
}

function ConfirmationSentView({
  labels,
  pending,
  onResend,
  error,
}: {
  labels: AcceptInvitationProps["labels"];
  pending: boolean;
  onResend: (() => void) | null;
  error: string | null;
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm" role="status">
        {labels.confirmationSent ?? labels.success}
      </p>
      {labels.resendConfirmation && onResend ? (
        <Button type="button" variant="outline" disabled={pending} onClick={onResend}>
          {pending ? labels.accepting : labels.resendConfirmation}
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

/**
 * Fragment-only invitation accept (REQ-2714 / ADR-0047).
 * Token lives in memory; never Server Action / RSC / storage / logs.
 */
export function AcceptInvitation({
  invitationId,
  endpoint,
  holdEndpoint,
  holdVariant,
  signInHref,
  onboardingHref,
  labels,
}: AcceptInvitationProps) {
  // The token lives in the URL fragment, which the server never sees. The
  // snapshot is memoized per path inside readFragmentToken, so the value is
  // stable across renders even after the scrub effect clears the hash.
  const fragmentToken = useSyncExternalStore(
    () => () => {},
    readFragmentToken,
    () => null,
  );
  const ready = useHydrated();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [confirmSent, setConfirmSent] = useState(false);
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
  // The last submitted token: lets the confirmation-sent state resend the
  // accept (which re-mails the invited inbox) after the fragment is gone.
  // In-memory state only — the value is never rendered.
  const [heldToken, setHeldToken] = useState<string | null>(null);
  // Whether a claim cookie was parked for this invitation+variant — the
  // fragment-less revisit signal that keeps the accept button available.
  const claimFlagged = useSyncExternalStore(
    () => () => {},
    () => (holdEndpoint && holdVariant ? hasInvitationClaimFlag(invitationId, holdVariant) : false),
    () => false,
  );

  useClaimParking(fragmentToken, holdEndpoint, holdVariant);

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

  const redirectToAuth = (target: string) => {
    const { pathname, search } = window.location;
    const returnTo = `${pathname}${search}${heldFragment.current ?? ""}`;
    window.location.assign(`${target}?${new URLSearchParams({ returnTo }).toString()}`);
  };

  // `held` may be null: the parked claim cookie then supplies the token
  // server-side (revisit without a fragment).
  const submit = (held: string | null) => {
    setError(null);
    startTransition(async () => {
      if (held !== null) {
        setHeldToken(held);
      }
      // Marked consumed immediately so remounts cannot re-use it.
      setConsumed(true);
      try {
        const csrf = readCsrfFromDocument();
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
        const outcome = await postAcceptance(endpoint, invitationId, held, csrf);
        if (outcome.kind === "unauthorized" && signInHref) {
          redirectToAuth(signInHref);
          return;
        }
        if (outcome.kind === "onboarding" && onboardingHref) {
          redirectToAuth(onboardingHref);
          return;
        }
        if (outcome.kind === "confirmation_sent") {
          setConfirmSent(true);
          return;
        }
        if (outcome.kind !== "success") {
          setError(labels.error);
          return;
        }
        setConfirmSent(false);
        setSuccess(true);
        setOperationId(outcome.operationId);
      } catch {
        setError(labels.error);
      }
    });
  };

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

  // The button stays available while either the in-memory token or a parked
  // claim cookie can answer for this invitation.
  const canSubmit = token !== null || claimFlagged;

  if (confirmSent) {
    return (
      <ConfirmationSentView
        labels={labels}
        pending={pending}
        onResend={
          heldToken !== null || claimFlagged
            ? () => {
                submit(heldToken);
              }
            : null
        }
        error={error}
      />
    );
  }

  if (!canSubmit && !consumed) {
    return (
      <p className="text-muted-foreground text-sm" role="status">
        {labels.missingToken}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {canSubmit ? (
        <Button
          type="button"
          disabled={pending}
          onClick={() => {
            submit(token);
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
