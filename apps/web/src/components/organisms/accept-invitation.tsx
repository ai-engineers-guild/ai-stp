"use client";

import { useEffect, useState, useTransition } from "react";

import { Button } from "@/components/atoms/button";
import { MutationReference } from "@/components/molecules/mutation-reference";
import { CSRF_COOKIE } from "@/lib/auth/cookies";

type AcceptInvitationProps = {
  invitationId: string;
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
export function AcceptInvitation({ invitationId, labels }: AcceptInvitationProps) {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [operationId, setOperationId] = useState<string | null>(null);
  const [consumed, setConsumed] = useState(false);

  useEffect(() => {
    const found = readFragmentToken();
    setToken(found);
    setReady(true);
    if (found) {
      scrubFragment();
    }
  }, []);

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
              // Drop from React state immediately so remounts cannot re-use it.
              setToken(null);
              setConsumed(true);
              try {
                const csrf = readCsrfFromDocument();
                if (!csrf || !held) {
                  setError(labels.error);
                  return;
                }
                const idempotencyKey = crypto.randomUUID().replaceAll("-", "");
                const response = await fetch(
                  `/api/grants/invitations/${encodeURIComponent(invitationId)}/accept`,
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
