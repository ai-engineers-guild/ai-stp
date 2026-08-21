/* eslint-disable no-restricted-syntax -- root 404 has no locale catalog (REQ-3107) */
import { NotFoundRickroll } from "@/components/molecules/not-found-rickroll";

/**
 * Locale is not available on the root 404. English is the agreed fallback.
 * The localized page lives at `app/[locale]/not-found.tsx`.
 */
export default function RootNotFound() {
  return (
    <html lang="en">
      <body className="bg-background text-foreground m-0 flex min-h-screen items-center justify-center p-6 font-sans">
        <main className="flex w-full max-w-xl flex-col gap-6">
          <h1 className="text-3xl font-medium tracking-tight">Page not found</h1>
          <NotFoundRickroll label="Never Gonna Give You Up" />
          <a className="text-sm underline" href="/">
            Home
          </a>
        </main>
      </body>
    </html>
  );
}
