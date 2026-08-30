"use client";

import { useLocale, useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/atoms/dialog";
import { KeyboardNavigation } from "@/components/molecules/keyboard-navigation";
import { ThemeToggle } from "@/components/molecules/theme-toggle";
import { AccountControl } from "@/components/organisms/account-drawer";
import { Link, usePathname, useRouter } from "@/lib/i18n/navigation";
import type { AppLocale } from "@/lib/i18n/routing";
import { isShellPrefetchHref } from "@/lib/prefetch-policy";
import { siteNavigation, type NavItem } from "@/lib/projection/navigation";
import { useSessionPresence } from "@/lib/auth/use-session-presence";
import { useUiSlice } from "@/lib/stores/ui-slice";
import { UI } from "@/lib/ui-selectors";
import { useHydrated } from "@/lib/use-hydrated";
import { SITE_NAME } from "@/lib/site";
import { Icon } from "@/theme/icons";

type SiteHeaderProps = {
  docsHref: string;
};

/**
 * The header no longer takes a server-rendered `signedIn`. It used to, and the
 * shell read the cookie to supply it — inside a tree Next builds as SSG, where
 * a cookie cannot honestly be read. Presence is asked at request time now, from
 * `/api/session`, after hydration.
 */
export function SiteHeader({ docsHref }: SiteHeaderProps) {
  const t = useTranslations("nav");
  const locale = useLocale() as AppLocale;
  const pathname = usePathname();
  const router = useRouter();
  const signedInHint = useSessionPresence();
  const hydrated = useHydrated();

  // The first client render must be byte-for-byte compatible with the static
  // HTML, which is always the signed-out shell. Only after hydration may the
  // answer from `/api/session` change what is shown.
  const isSignedIn = hydrated && signedInHint;
  const navigation = siteNavigation({ signedIn: isSignedIn, docsHref });
  const accountMenuItems = new Set<string>([
    UI.navigation.objects,
    UI.navigation.access,
    UI.navigation.reports,
    UI.navigation.devices,
  ]);
  const primaryNavigation = navigation.filter(
    (item) =>
      item.ui !== UI.navigation.contact &&
      item.ui !== UI.navigation.account &&
      !accountMenuItems.has(item.ui),
  );
  const contactItem = navigation.find((item) => item.ui === UI.navigation.contact);

  function switchLocale(next: AppLocale) {
    router.replace(pathname, { locale: next });
  }

  const nextLocale: AppLocale = locale === "en" ? "ru" : "en";
  const mobileNavOpen = useUiSlice((s) => s.mobileNavOpen);
  const setMobileNavOpen = useUiSlice((s) => s.setMobileNavOpen);
  const mobileItems = [...primaryNavigation.slice(1), ...(contactItem ? [contactItem] : [])];

  return (
    <header
      id="site-header"
      data-ui={UI.shell.header}
      className="border-border bg-background sticky top-0 z-40 overflow-x-clip border-b"
    >
      <KeyboardNavigation
        accountHref={isSignedIn ? "/account" : "/login"}
        contactEnabled={contactItem !== undefined}
      />
      <div className="mx-auto flex h-16 max-w-6xl min-w-0 items-center justify-between gap-2 px-4 sm:gap-4">
        <nav
          data-ui={UI.shell.primaryNav}
          aria-label={t("primaryLabel")}
          className="flex min-w-0 items-center gap-2 sm:gap-5"
        >
          <MobilePrimaryNav
            items={mobileItems}
            open={mobileNavOpen}
            onOpenChange={setMobileNavOpen}
            openLabel={t("openMenu")}
            closeLabel={t("closeMenu")}
            title={t("primaryLabel")}
            labelFor={(item) => t(item.labelKey)}
          />
          <Link
            data-ui={UI.navigation.home}
            href="/"
            className="flex min-w-0 items-center gap-2 text-sm font-medium tracking-tight transition-colors"
            prefetch={isShellPrefetchHref("/")}
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
          {primaryNavigation.slice(1).map((item) => {
            const className =
              "text-muted-foreground hover:text-foreground hidden text-sm transition-colors sm:inline";
            return item.external ? (
              <a key={item.ui} data-ui={item.ui} href={item.href} className={className}>
                {t(item.labelKey)}
              </a>
            ) : (
              <Link
                key={item.ui}
                data-ui={item.ui}
                href={item.href}
                className={className}
                prefetch={isShellPrefetchHref(item.href)}
              >
                {t(item.labelKey)}
              </Link>
            );
          })}
        </nav>
        <div className="flex shrink-0 items-center gap-1 sm:gap-3">
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

export function MobilePrimaryNav({
  items,
  open,
  onOpenChange,
  openLabel,
  closeLabel,
  title,
  labelFor,
}: {
  items: readonly NavItem[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  openLabel: string;
  closeLabel: string;
  title: string;
  labelFor: (item: NavItem) => string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button
          type="button"
          size="icon"
          variant="outline"
          className="size-11 sm:hidden"
          aria-label={openLabel}
          aria-expanded={open}
          aria-controls="mobile-primary-nav"
        >
          <Icon name="list" size="md" />
        </Button>
      </DialogTrigger>
      <DialogContent
        closeLabel={closeLabel}
        className="top-0 left-0 h-dvh max-h-dvh w-[min(20rem,calc(100vw-1.5rem))] max-w-none translate-x-0 translate-y-0 gap-0 overflow-y-auto rounded-none p-4 pt-14 sm:hidden sm:rounded-none"
      >
        <DialogTitle className="sr-only">{title}</DialogTitle>
        <nav id="mobile-primary-nav" aria-label={title} className="flex flex-col gap-1">
          {items.map((item) => {
            const className =
              "text-foreground hover:bg-muted focus-visible:ring-ring flex min-h-11 items-center rounded-sm px-3 text-sm outline-none focus-visible:ring-2";
            return item.external ? (
              <a
                key={item.ui}
                data-ui={item.ui}
                href={item.href}
                className={className}
                onClick={() => {
                  onOpenChange(false);
                }}
              >
                {labelFor(item)}
              </a>
            ) : (
              <Link
                key={item.ui}
                data-ui={item.ui}
                href={item.href}
                className={className}
                prefetch={isShellPrefetchHref(item.href)}
                onClick={() => {
                  onOpenChange(false);
                }}
              >
                {labelFor(item)}
              </Link>
            );
          })}
        </nav>
      </DialogContent>
    </Dialog>
  );
}
