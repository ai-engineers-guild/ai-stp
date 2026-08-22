import { Suspense } from "react";
import { getTranslations } from "next-intl/server";

import { SiteHeader } from "@/components/layouts/site-header";
import { ProjectionDock } from "@/components/molecules/projection-dock";
import { CookieConsent } from "@/components/organisms/cookie-consent";
import { getEnv } from "@/lib/env";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";
import { isFeatureEnabled } from "@/lib/features/gate";
import { SITE_NAME } from "@/lib/site";

type AppShellProps = {
  children: React.ReactNode;
  locale: string;
};

export async function AppShell({ children, locale }: AppShellProps) {
  const t = await getTranslations("a11y");
  const tf = await getTranslations("footer");
  const tc = await getTranslations("consent");
  const tm = await getTranslations("machine");
  const docsHref = getEnv().AI_STP_USER_DOCS_URL;
  const saasPublicPages = isFeatureEnabled("saas_public_pages");

  return (
    <div
      data-ui={UI.shell.root}
      className="grid min-h-dvh min-w-0 grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr_auto] overflow-x-clip"
    >
      <a
        href="#main-content"
        className="focus:bg-background focus:ring-ring sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:rounded-sm focus:px-3 focus:py-2 focus:ring-2"
      >
        {t("skipToContent")}
      </a>
      <SiteHeader docsHref={docsHref} />
      <main
        id={UI.shell.main}
        data-ui={UI.shell.main}
        className="mx-auto w-full max-w-6xl min-w-0 px-4 py-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] sm:px-6"
      >
        {children}
      </main>
      <footer
        id="site-footer"
        data-ui={UI.shell.footer}
        className="border-border bg-background border-t"
      >
        <div
          className={`mx-auto grid max-w-6xl gap-10 px-4 py-10 sm:px-6 ${
            saasPublicPages ? "lg:grid-cols-[1.25fr_1fr_1fr_1fr]" : "lg:grid-cols-[1.25fr_1fr]"
          }`}
        >
          <div className="space-y-4">
            <Link href="/" className="inline-flex items-center gap-3 font-medium">
              <img
                src="/brand/logo-mark-64.png"
                alt=""
                width={32}
                height={32}
                className="h-8 w-8"
              />
              <span>{SITE_NAME}</span>
            </Link>
            <p className="text-muted-foreground max-w-xs text-sm leading-relaxed">
              {tf("summary")}
            </p>
            <a href="/llms.txt" className="font-mono text-xs underline underline-offset-4">
              {tm("llms")}
            </a>
          </div>
          <FooterColumn
            title={tf("product")}
            links={[
              { label: tf("catalog"), href: "/catalog" },
              { label: tf("services"), href: "/services" },
              { label: tf("docs"), href: docsHref },
              ...(isFeatureEnabled("content_hub")
                ? [{ label: tf("content"), href: "/content" }]
                : []),
            ]}
          />
          {saasPublicPages ? (
            <>
              <FooterColumn
                title={tf("company")}
                links={[
                  { label: tf("contact"), href: "/contact" },
                  { label: tf("privacy"), href: "/legal/privacy" },
                ]}
              />
              <FooterColumn
                title={tf("legal")}
                links={[
                  { label: tf("cookies"), href: "/legal/cookies" },
                  { label: tf("serviceRules"), href: "/legal/service-rules" },
                  { label: tf("licensing"), href: "/legal/licensing" },
                ]}
              />
            </>
          ) : null}
        </div>
        <div className="border-border border-t">
          <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 py-4 sm:px-6 md:flex-row">
            <p className="text-muted-foreground font-mono text-[11px] tracking-wide">
              {tf("licenseLine", { year: 2026 })}
            </p>
            <div
              data-ui={UI.navigation.shortcuts}
              className="text-muted-foreground hidden items-center gap-2 font-mono text-[11px] lg:flex"
            >
              <span>{tf("shortcuts")}</span>
              {saasPublicPages ? (
                <kbd className="border-border rounded-sm border px-1.5 py-0.5">
                  {tf("shortcutContact")}
                </kbd>
              ) : null}
              <kbd className="border-border rounded-sm border px-1.5 py-0.5">
                {tf("shortcutProfile")}
              </kbd>
              <kbd className="border-border rounded-sm border px-1.5 py-0.5">
                {tf("shortcutCatalog")}
              </kbd>
            </div>
          </div>
        </div>
      </footer>
      <Suspense fallback={null}>
        <ProjectionDock locale={locale} />
      </Suspense>
      {process.env.NEXT_PUBLIC_COOKIE_CONSENT_ENABLED !== "false" ? (
        <CookieConsent
          privacyHref={`/${locale}/legal/privacy`}
          labels={{
            title: tc("title"),
            body: tc("body"),
            necessary: tc("necessary"),
            analytics: tc("analytics"),
            marketing: tc("marketing"),
            accept: tc("accept"),
            reject: tc("reject"),
            save: tc("save"),
            manage: tc("manage"),
            privacy: tc("privacy"),
          }}
        />
      ) : null}
    </div>
  );
}

function FooterColumn({
  title,
  links,
}: {
  title: string;
  links: readonly { label: string; href: string }[];
}) {
  return (
    <section className="space-y-4">
      <h2 className="font-mono text-xs font-medium tracking-wide uppercase">{title}</h2>
      <nav data-ui={UI.shell.footerNav} aria-label={title}>
        <ul className="space-y-3 text-sm">
          {links.map(({ label, href }) => (
            <li key={href}>
              {isExternalHref(href) ? (
                <a
                  href={href}
                  className="text-muted-foreground hover:text-foreground underline-offset-4 hover:underline"
                >
                  {label}
                </a>
              ) : (
                <Link
                  href={href}
                  className="text-muted-foreground hover:text-foreground underline-offset-4 hover:underline"
                >
                  {label}
                </Link>
              )}
            </li>
          ))}
        </ul>
      </nav>
    </section>
  );
}

function isExternalHref(href: string): boolean {
  return href.startsWith("http://") || href.startsWith("https://");
}
