import { headers } from "next/headers";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layouts/app-shell";
import { requireSession } from "@/lib/auth/require-session";
import { COMPILED_FEATURE_PROFILE } from "@/lib/features/compiled";

/** Corporate pages that render without an active session. */
const CORPORATE_PUBLIC_PAGES = new Set(["login", "device-login", "onboarding"]);

type SiteLayoutProps = {
  children: ReactNode;
  params: Promise<{ locale: string }>;
};

/**
 * Human projection shell. It is a separate route segment from the machine
 * tree, so the client router never reuses one projection's chrome for the
 * other (ADR-0056).
 *
 * In the corporate hub every page requires an active session: the middleware
 * checks the cookie and this layout validates it against the API, so an
 * expired session always lands on the authentication screen.
 */
export default async function SiteLayout({ children, params }: SiteLayoutProps) {
  const { locale } = await params;
  if (COMPILED_FEATURE_PROFILE === "corporate_hub") {
    const pathname = (await headers()).get("x-ai-stp-request-pathname") ?? "";
    const segments = pathname.split("/").filter(Boolean);
    const page = segments[1] === "corporate" ? segments[2] : segments[1];
    if (!CORPORATE_PUBLIC_PAGES.has(page ?? "")) {
      await requireSession(locale, pathname || `/${locale}/corporate`);
    }
  }
  return <AppShell locale={locale}>{children}</AppShell>;
}
