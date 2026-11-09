"use client";

/* eslint-disable no-restricted-syntax -- root 500 has no locale catalog (REQ-3107) */

/**
 * Root global-error (SPEC-031 REQ-3107).
 * Minimal 500 page outside the design-token tree: uses system colors only.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const requestId = error.digest;

  return (
    <html lang="en">
      <body className="m-0 flex min-h-screen items-center justify-center bg-background p-6 font-sans text-foreground">
        <main className="w-full max-w-md">
          <p className="font-mono text-xs text-muted-foreground">HTTP 500</p>
          <h1 className="mt-3 text-3xl font-medium tracking-tight">Something went wrong</h1>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            Try again. No internal error details are shown on this page.
          </p>
          {requestId ? (
            <p className="mt-4 font-mono text-xs text-muted-foreground">request id: {requestId}</p>
          ) : null}
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              className="rounded-sm bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
              onClick={() => {
                reset();
              }}
            >
              Try again
            </button>
            <a
              href="/"
              className="rounded-sm border border-border px-4 py-2 text-sm text-foreground no-underline"
            >
              Home
            </a>
          </div>
        </main>
      </body>
    </html>
  );
}
