"use client";

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
      <body className="bg-background text-foreground m-0 flex min-h-screen items-center justify-center p-6 font-sans">
        <main className="w-full max-w-md">
          <p className="text-muted-foreground font-mono text-xs">HTTP 500</p>
          <h1 className="mt-3 text-3xl font-medium tracking-tight">Something went wrong</h1>
          <p className="text-muted-foreground mt-3 text-sm leading-relaxed">
            Try again. No internal error details are shown on this page.
          </p>
          {requestId ? (
            <p className="text-muted-foreground mt-4 font-mono text-xs">request id: {requestId}</p>
          ) : null}
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              className="bg-primary text-primary-foreground rounded-sm px-4 py-2 text-sm font-medium"
              onClick={() => {
                reset();
              }}
            >
              Try again
            </button>
            <a
              href="/"
              className="border-border text-foreground rounded-sm border px-4 py-2 text-sm no-underline"
            >
              Home
            </a>
          </div>
        </main>
      </body>
    </html>
  );
}
