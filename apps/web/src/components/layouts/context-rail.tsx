"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/atoms/dialog";
import { RailItems, railItemClass, type RailItem } from "@/components/layouts/context-rail-items";
import { resolveCorporateRail } from "@/lib/corporate-rail";
import { COMPILED_FEATURE_PROFILE } from "@/lib/features/compiled";
import { corporateHref } from "@/lib/features/corporate-path";
import { Link, usePathname } from "@/lib/i18n/navigation";
import { localeNeutralPathname } from "@/lib/i18n/locale-path";
import { siteNavigation, isPrimaryNavigationActive } from "@/lib/projection/navigation";
import { useSessionUiSlice } from "@/lib/stores/session-ui-slice";
import { useUiSlice } from "@/lib/stores/ui-slice";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/cn";
import { UI } from "@/lib/ui-selectors";
import { Icon, type IconName } from "@/theme/icons";

export type { RailItem };

const siteIcons: Record<string, IconName> = {
  home: "cards",
  catalog: "objects",
  services: "globe",
  docs: "code",
  content: "list",
  contact: "mail",
};

/** Shared Human navigation, extended from the original corporate rail (ADR-0219). */
export function ContextRail({
  docsHref,
  allowedPages,
  serverAuthorized = false,
  corporate = COMPILED_FEATURE_PROFILE === "corporate_hub",
}: {
  docsHref: string;
  allowedPages?: readonly string[] | null;
  serverAuthorized?: boolean;
  corporate?: boolean;
}) {
  const nav = useTranslations("nav");
  const hub = useTranslations("hub");
  const pathname = localeNeutralPathname(usePathname());
  const signedIn = useSessionUiSlice((s) => s.signedInHint);
  const hydrated = useHydrated();
  const availability = useSessionUiSlice((s) => s.corporateNavPages);
  const setAvailability = useSessionUiSlice((s) => s.setCorporateNavPages);
  const [verifiedPages, setVerifiedPages] = useState<readonly string[] | null>(() =>
    allowedPages === undefined ? availability : allowedPages,
  );
  const initialPath = useRef(pathname);
  const initialPages = useRef(allowedPages);
  useEffect(() => {
    if (!corporate || /\/(?:login|signup)(?:\/|$)/.test(pathname)) return;
    if (
      pathname === initialPath.current &&
      allowedPages === initialPages.current &&
      allowedPages !== undefined &&
      allowedPages !== null
    )
      return;
    const aborter = new AbortController();
    void fetch("/api/corporate/navigation", {
      cache: "no-store",
      credentials: "same-origin",
      signal: aborter.signal,
    })
      .then(async (response) => {
        if (response.status === 401 || response.status === 403) {
          if (!aborter.signal.aborted) {
            setAvailability([]);
            setVerifiedPages([]);
          }
          return;
        }
        if (!response.ok) return;
        const body = (await response.json()) as { pages?: unknown };
        if (aborter.signal.aborted) return;
        const pages = Array.isArray(body.pages)
          ? body.pages.filter((id): id is string => typeof id === "string")
          : [];
        setAvailability(pages);
        setVerifiedPages(pages);
      })
      .catch(() => {
        /* Keep the last verified navigation during transient revalidation. */
      });
    return () => {
      aborter.abort();
    };
  }, [corporate, pathname, allowedPages, setAvailability]);
  const pageIds = verifiedPages ?? [];
  const [mainNavigationPath, setMainNavigationPath] = useState<string | null>(null);
  const corporateNav = resolveCorporateRail(pathname, pageIds, mainNavigationPath === pathname);
  const personalIds: string[] = [
    UI.navigation.objects,
    UI.navigation.access,
    UI.navigation.reports,
    UI.navigation.devices,
    UI.navigation.account,
  ];
  const publicItems = siteNavigation({ signedIn: hydrated && signedIn, docsHref })
    .filter((item) => !personalIds.includes(item.ui))
    .map((item): RailItem => ({
      id: item.ui,
      href: corporateHref(item.href),
      label: nav(item.labelKey),
      icon: siteIcons[item.labelKey] ?? "list",
      active: isPrimaryNavigationActive({ ...item, href: corporateHref(item.href) }, pathname),
      external: item.external,
    }));
  const allItems: RailItem[] = corporate
    ? corporateNav.entries.map((entry) => ({
        ...entry,
        id: `corporate-nav-${entry.id}`,
        label: hub(entry.label),
        children: entry.children?.map((child) => ({
          ...child,
          id: `corporate-nav-${child.id}`,
          label: hub(child.label),
        })),
      }))
    : publicItems;
  // Administration is a leaf link pinned under a divider at the rail bottom.
  const items = allItems.map((item) =>
    item.id === "corporate-nav-administration" ? { ...item, pinned: true } : item,
  );
  const scope = corporate ? corporateNav.context : "saas";
  const corporateBack = corporate ? corporateNav.back : null;
  const parent = publicItems.find(
    (item) => item.active && pathname !== item.href && pathname.startsWith(`${item.href}/`),
  );
  const backTarget = corporateBack ?? (!corporate && parent ? parent : null);
  const back = backTarget
    ? {
        href: backTarget.href,
        label: nav("backToSection", {
          section: corporateBack ? hub(corporateBack.label) : (parent?.label ?? ""),
        }),
      }
    : null;
  if (
    corporate &&
    ((!serverAuthorized && !(hydrated && signedIn)) ||
      (hydrated && !signedIn && availability !== null) ||
      !items.length ||
      /\/(?:login|signup)(?:\/|$)/.test(pathname))
  )
    return null;
  return (
    <ContextSidebar
      {...{ corporate, pathname, items, scope, back }}
      // The landing hero is the only public page without a side rail; the
      // mobile trigger stays so primary navigation remains reachable there.
      suppressAside={!corporate && pathname === "/"}
      onShowMainNavigation={() => {
        setMainNavigationPath(pathname);
      }}
      onNavigate={() => {
        setMainNavigationPath(null);
      }}
    />
  );
}

/** Presentation shared by the app and Storybook; authorization stays in ContextRail. */
type ContextSidebarProps = {
  corporate: boolean;
  pathname: string;
  items: RailItem[];
  scope: string;
  back: false | { href: string; label: string } | null;
  suppressAside?: boolean;
  onShowMainNavigation?: () => void;
  onNavigate?: () => void;
};
export function ContextSidebar({
  corporate,
  pathname,
  items,
  scope,
  back,
  suppressAside = false,
  onShowMainNavigation,
  onNavigate,
}: ContextSidebarProps) {
  const nav = useTranslations("nav");
  const hub = useTranslations("hub");
  const hydrated = useHydrated();
  const storedCollapsed = useUiSlice((s) => s.sidebarCollapsed);
  const collapsed = hydrated && storedCollapsed;
  const restoreSidebar = useUiSlice((s) => s.restoreSidebar);
  const [openPath, setOpenPath] = useState<string | null>(null);
  const [navigatedPath, setNavigatedPath] = useState(pathname);
  if (navigatedPath !== pathname) {
    setNavigatedPath(pathname);
    setOpenPath(null);
  }
  const open = openPath === pathname;
  const closeMenu = () => {
    setOpenPath(null);
    onNavigate?.();
  };
  useEffect(() => {
    restoreSidebar();
  }, [restoreSidebar]);
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1024px)");
    const closeOnDesktop = () => {
      if (desktop.matches) setOpenPath(null);
    };
    closeOnDesktop();
    desktop.addEventListener("change", closeOnDesktop);
    return () => {
      desktop.removeEventListener("change", closeOnDesktop);
    };
  }, []);
  function contents(isCollapsed: boolean, mobile = false) {
    return (
      <>
        {scope === "administration" && onShowMainNavigation ? (
          <Button
            type="button"
            variant="ghost"
            className={cn(
              railItemClass,
              "w-full justify-start",
              isCollapsed && "justify-center px-0",
            )}
            aria-label={nav("backToNavigation")}
            title={nav("backToNavigation")}
            onClick={onShowMainNavigation}
          >
            <Icon name="arrowLeft" size="md" />
            <span className={isCollapsed ? "sr-only" : ""}>{nav("backToNavigation")}</span>
          </Button>
        ) : null}
        {back ? (
          <Link
            data-ui={UI.navigation.back}
            href={back.href}
            className={cn(railItemClass, isCollapsed && "justify-center px-0")}
            title={back.label}
            onClick={closeMenu}
          >
            <Icon name="arrowLeft" size="md" />
            <span className={isCollapsed ? "sr-only" : ""}>{back.label}</span>
          </Link>
        ) : null}
        {scope === "administration" && !isCollapsed ? (
          <h2 className="px-3 pt-3 pb-2 text-lg font-medium">{hub("administration")}</h2>
        ) : null}
        <RailItems
          key={pathname}
          scope={`${mobile ? "mobile" : "desktop"}-${scope}`}
          items={items}
          collapsed={isCollapsed}
          onNavigate={closeMenu}
        />
      </>
    );
  }
  return (
    <>
      {suppressAside ? null : (
        <aside
          data-ui={UI.shell.sidebar}
          data-collapsed={collapsed}
          className={cn(
            "border-border bg-background sticky top-14 hidden h-[calc(100dvh-3.5rem)] shrink-0 flex-col border-r lg:flex",
            collapsed ? "w-16" : "w-64",
          )}
        >
          <nav
            id="desktop-context-navigation"
            data-ui={corporate ? UI.corporate.contextNavList : UI.shell.primaryNav}
            aria-label={nav("primaryLabel")}
            className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-2 py-4"
          >
            {contents(collapsed)}
          </nav>
        </aside>
      )}
      <div className="fixed top-2.5 left-4 z-50 lg:hidden">
        <Dialog
          open={open}
          onOpenChange={(next) => {
            setOpenPath(next ? pathname : null);
          }}
        >
          <DialogTrigger asChild>
            <Button
              type="button"
              size="icon"
              variant="outline"
              className="size-11"
              aria-label={nav("openMenu")}
            >
              <Icon name="list" size="md" />
            </Button>
          </DialogTrigger>
          <DialogContent
            aria-describedby={undefined}
            closeLabel={nav("closeMenu")}
            className="top-0 left-0 flex h-dvh max-h-dvh w-[min(20rem,calc(100vw-1.5rem))] max-w-none translate-x-0 translate-y-0 flex-col gap-4 rounded-none p-4 pt-14 sm:rounded-none lg:hidden"
          >
            <DialogTitle>{nav("primaryLabel")}</DialogTitle>
            <nav
              id="mobile-context-navigation"
              aria-label={nav("primaryLabel")}
              className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto"
            >
              {contents(false, true)}
            </nav>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
}
