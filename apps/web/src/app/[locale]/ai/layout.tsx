import { Suspense, type ReactNode } from "react";
import { getTranslations } from "next-intl/server";

import { MachineFooter, MachineHeader } from "@/components/layouts/machine-chrome";
import { ProjectionDock } from "@/components/molecules/projection-dock";
import { readSession } from "@/lib/auth/session";
import { getEnv } from "@/lib/env";
import { UI } from "@/lib/ui-selectors";

type MachineLayoutProps = {
  children: ReactNode;
  params: Promise<{ locale: string }>;
};

/**
 * Machine projection shell. A real route segment, not a rewrite: the two
 * projections own separate layouts, so the client router cannot serve one
 * projection's chrome with the other's page (ADR-0056).
 */
export default async function MachineLayout({ children, params }: MachineLayoutProps) {
  const { locale } = await params;
  const t = await getTranslations("a11y");
  const session = await readSession();
  const docsHref = getEnv().AI_STP_USER_DOCS_URL;

  return (
    <div
      data-ui={UI.shell.root}
      className="grid min-h-dvh min-w-0 grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr_auto]"
    >
      <a
        href="#main-content"
        className="focus:bg-background focus:ring-ring sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:rounded-sm focus:px-3 focus:py-2 focus:ring-2"
      >
        {t("skipToContent")}
      </a>
      <MachineHeader signedIn={session !== null} locale={locale} docsHref={docsHref} />
      <main
        id={UI.shell.main}
        data-ui={UI.shell.main}
        className="mx-auto w-full max-w-4xl min-w-0 px-4 py-6 font-mono sm:px-6"
      >
        {children}
      </main>
      <MachineFooter />
      <Suspense fallback={null}>
        <ProjectionDock locale={locale} />
      </Suspense>
    </div>
  );
}
