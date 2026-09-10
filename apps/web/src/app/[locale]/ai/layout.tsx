import { Suspense, type ReactNode } from "react";
import { getTranslations } from "next-intl/server";

import { MachineFooter, MachineHeader } from "@/components/layouts/machine-chrome";
import { ContextSurfaceNav } from "@/components/molecules/context-surface-nav";
import { ProductContextSwitcher } from "@/components/molecules/product-context-switcher";
import { ProjectionDock } from "@/components/molecules/projection-dock";
import { ProjectionDockEnhancer } from "@/components/molecules/projection-dock-enhancer";
import { readSession } from "@/lib/auth/session";
import { contextStatus, loadProductContext } from "@/lib/product-context-server";
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
  const productContext = await loadProductContext();
  const tx = await getTranslations("context");

  return (
    <div
      data-ui={UI.shell.root}
      className="grid min-h-dvh min-w-0 grid-cols-[minmax(0,1fr)] grid-rows-[auto_auto_1fr_auto]"
    >
      <a
        href="#main-content"
        className="focus:bg-background focus:ring-ring sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:rounded-sm focus:px-3 focus:py-2 focus:ring-2"
      >
        {t("skipToContent")}
      </a>
      <MachineHeader signedIn={session !== null} locale={locale} docsHref={docsHref} />
      <div className="min-h-[88px]">
        <ProductContextSwitcher
          {...productContext}
          labels={{
            selector: tx("selector"),
            local: tx("local"),
            mode: { personal: tx("personal"), corporate: tx("corporate") },
            loading: tx("loading"),
            failed: tx("failed"),
            partial: tx("partial"),
            forbidden: tx("forbidden"),
            stale: tx("stale"),
            unavailable: tx("unavailable"),
            unsupported: tx("unsupported"),
            empty: tx("empty"),
            unauthenticated: tx("unauthenticated"),
            switchFailed: tx("switchFailed"),
          }}
        />
        <ContextSurfaceNav
          context={productContext.context}
          status={contextStatus(productContext)}
          labels={{
            navigation: tx("surfaceNavigation"),
            projects: tx("surfaces.projects"),
            technology: tx("surfaces.technology"),
            landscape: tx("surfaces.landscape"),
            catalog: tx("surfaces.catalog"),
          }}
          reserveWhenHidden
        />
      </div>
      <main
        id={UI.shell.main}
        data-ui={UI.shell.main}
        className="mx-auto w-full max-w-4xl min-w-0 px-4 py-6 font-mono sm:px-6"
      >
        {children}
      </main>
      <MachineFooter />
      <ProjectionDock locale={locale} projection="machine" />
      <Suspense fallback={null}>
        <ProjectionDockEnhancer locale={locale} />
      </Suspense>
    </div>
  );
}
