import type { ReactNode } from "react";

import { AppShell } from "@/components/layouts/app-shell";

type SiteLayoutProps = {
  children: ReactNode;
  params: Promise<{ locale: string }>;
};

/**
 * Human projection shell. It is a separate route segment from the machine
 * tree, so the client router never reuses one projection's chrome for the
 * other (ADR-0056).
 */
export default async function SiteLayout({ children, params }: SiteLayoutProps) {
  const { locale } = await params;
  return <AppShell locale={locale}>{children}</AppShell>;
}
