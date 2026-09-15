import type { ReactNode } from "react";
import { CorporateHubNavigation } from "@/components/layouts/corporate-hub-navigation";
import { readCorporateContext } from "@/lib/api/corporate";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { ApiError } from "@/lib/api/errors";

export default async function CorporateHubLayout({ children }: { children: ReactNode }) {
  const session = await sessionCookieValue();
  let capabilities: string[] = [];
  try {
    capabilities = session ? ((await readCorporateContext(session))?.capabilities ?? []) : [];
  } catch (error) {
    // The page owns its error state; unavailable navigation must not expose forbidden links.
    if (!(error instanceof ApiError)) throw error;
  }
  return (
    <>
      <CorporateHubNavigation capabilities={capabilities} />
      {children}
    </>
  );
}
