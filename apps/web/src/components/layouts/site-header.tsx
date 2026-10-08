"use client";

import { useLocale, useTranslations } from "next-intl";
import { COMPILED_FEATURE_PROFILE } from "@/lib/features/compiled";
import { corporateHref } from "@/lib/features/corporate-path";

import { Button } from "@/components/atoms/button";
import { KeyboardNavigation } from "@/components/molecules/keyboard-navigation";
import { ThemeToggle } from "@/components/molecules/theme-toggle";
import { AccountControl } from "@/components/organisms/account-control";
import { Link, usePathname } from "@/lib/i18n/navigation";
import { localeNeutralPathname } from "@/lib/i18n/locale-path";
import type { AppLocale } from "@/lib/i18n/routing";
import { isShellPrefetchHref } from "@/lib/prefetch-policy";
import { siteNavigation } from "@/lib/projection/navigation";
import { useSessionPresence } from "@/lib/auth/use-session-presence";
import { UI } from "@/lib/ui-selectors";
import { useHydrated } from "@/lib/use-hydrated";
import { useSessionUiSlice } from "@/lib/stores/session-ui-slice";
import { useUiSlice } from "@/lib/stores/ui-slice";
import { cn } from "@/lib/cn";
import { SITE_NAME } from "@/lib/site";
import { Icon } from "@/theme/icons";

type SiteHeaderProps = {
  docsHref: string;
  corporateSessionVerified?: boolean;
  corporateNavigationPages?: readonly string[] | null;
};

/**
 * Account controls remain client-personalized for public/static pages. A
 * protected Corporate route supplies server-verified page IDs so its
 * navigation control is present in the first HTML.
 */
export function SiteHeader({
  docsHref,
  corporateSessionVerified = false,
  corporateNavigationPages,
}: SiteHeaderProps) {
  const t = useTranslations("nav");
  const locale = useLocale() as AppLocale;
  const signedInHint = useSessionPresence();
  const hydrated = useHydrated();
  const storedSidebarCollapsed = useUiSlice((s) => s.sidebarCollapsed);
  const setSidebarCollapsed = useUiSlice((s) => s.setSidebarCollapsed);
  const sidebarCollapsed = hydrated && storedSidebarCollapsed;

  // Account controls match the signed-out server snapshot during hydration;
  // protected Corporate navigation uses its separate server snapshot.
  const isSignedIn = hydrated && signedInHint;
  const corporate = COMPILED_FEATURE_PROFILE === "corporate_hub";
  const corporatePages = useSessionUiSlice((s) => s.corporateNavPages);
  const pathname = usePathname();
  const visibleCorporatePages = corporatePages ?? corporateNavigationPages;
  const hasSidebar =
    !corporate ||
    ((corporateSessionVerified || isSignedIn) &&
      Boolean(visibleCorporatePages?.length) &&
      !/\/(?:login|signup)(?:\/|$)/.test(pathname));
  const contactItem = siteNavigation({ signedIn: isSignedIn, docsHref }).find(
    (item) => item.ui === UI.navigation.contact,
  );

  function switchLocale(next: AppLocale) {
    // `usePathname` is normally locale-neutral, but corporate rewrites can
    // expose the localized segment. Strip it so next-intl does not build
    // `/ru/en/...` and the language control remains a real route switch.
    const route = localeNeutralPathname(window.location.pathname);
    window.location.assign(
      `/${next}${route === "/" ? "" : route}${window.location.search}${window.location.hash}`,
    );
  }

  const nextLocale: AppLocale = locale === "en" ? "ru" : "en";

  return (
    <header
      id="site-header"
      data-ui={UI.shell.header}
      className="border-border bg-background sticky top-0 z-40 border-b"
    >
      <KeyboardNavigation
        accountHref={isSignedIn ? "/account" : "/login"}
        contactEnabled={contactItem !== undefined}
      />
      <div className="flex h-14 min-w-0 items-center justify-between gap-2 px-4 sm:gap-4 sm:px-6 lg:px-8">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          {hasSidebar ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="hidden size-11 lg:inline-flex"
              data-ui={UI.navigation.collapse}
              aria-label={t(sidebarCollapsed ? "expandSidebar" : "collapseSidebar")}
              aria-expanded={!sidebarCollapsed}
              aria-controls="desktop-context-navigation"
              onClick={() => {
                setSidebarCollapsed(!sidebarCollapsed);
              }}
            >
              <Icon name={sidebarCollapsed ? "chevronRight" : "chevronLeft"} size="md" />
            </Button>
          ) : null}
          <Link
            href={corporateHref("/")}
            aria-label={SITE_NAME}
            className={cn(
              "flex min-w-0 items-center gap-2 text-sm font-medium",
              hasSidebar && "ml-14 lg:ml-0",
            )}
            prefetch={!corporate && isShellPrefetchHref("/")}
          >
            {/* Loop mark: abstract 5-node ring (club of five / human in the loop) */}
            <img
              src="/brand/logo-mark-64.png"
              alt=""
              width={28}
              height={28}
              className="h-7 w-7 shrink-0"
              aria-hidden
            />
            <span className="hidden min-[400px]:inline">{SITE_NAME}</span>
          </Link>
        </div>
        <div className="flex shrink-0 items-center gap-1 sm:gap-3">
          {corporate && (
            <Link
              href="/corporate/overview"
              className="text-primary hover:text-primary-hover inline-flex items-center text-sm font-bold tracking-tight no-underline transition-colors focus-visible:rounded-sm"
              prefetch={false}
            >
              <span className="corporate-header-label">{t("corporateHub")}</span>
            </Link>
          )}
          <button
            id={UI.navigation.locale}
            data-ui={UI.navigation.locale}
            type="button"
            className="hover:bg-muted focus-visible:ring-ring inline-flex size-11 items-center justify-center rounded-sm font-mono text-xs font-medium uppercase transition-colors focus-visible:ring-2 focus-visible:outline-none"
            title={`${t("language")}: ${nextLocale.toUpperCase()}`}
            aria-label={`${t("language")}: ${nextLocale.toUpperCase()}`}
            onClick={() => {
              switchLocale(nextLocale);
            }}
          >
            {nextLocale}
          </button>
          <ThemeToggle />
          {contactItem ? (
            <Button asChild size="icon" variant="outline" className="hidden size-11 sm:inline-flex">
              <Link
                data-ui={contactItem.ui}
                href={contactItem.href}
                title={t("contactHint")}
                aria-label={t("contactHint")}
                prefetch={isShellPrefetchHref(contactItem.href)}
              >
                <Icon name="mail" size="md" />
                <span className="sr-only">
                  {t("contact")}, {t("contactKey")}
                </span>
              </Link>
            </Button>
          ) : null}
          <AccountControl signedIn={isSignedIn} />
        </div>
      </div>
    </header>
  );
}
