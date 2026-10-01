"use client";

import { useEffect, useRef, useState } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/atoms/dialog";
import { resolveCorporateRail } from "@/lib/corporate-navigation";
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

export type RailItem = {
  id: string;
  href: string;
  label: string;
  icon: IconName;
  active: boolean;
  external?: boolean | undefined;
  children?: RailItem[] | undefined;
};
const siteIcons: Record<string, IconName> = {
  home: "cards",
  catalog: "objects",
  services: "globe",
  docs: "code",
  content: "list",
  contact: "mail",
};
const itemClass =
  "text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring flex min-h-11 min-w-0 items-center gap-3 rounded-sm px-3 text-sm outline-none focus-visible:ring-2";
const activeClass =
  "bg-primary/5 dark:bg-primary/10 text-primary font-medium before:absolute before:inset-y-2 before:left-0 before:w-1 before:rounded-sm before:bg-primary";

function RailItems({
  items,
  collapsed,
  scope,
  onNavigate,
}: {
  items: RailItem[];
  collapsed: boolean;
  scope: string;
  onNavigate: () => void;
}) {
  const t = useTranslations("nav");
  const [disclosures, setDisclosures] = useState<Record<string, boolean>>({});
  function link(item: RailItem, child = false) {
    const props = {
      "data-ui":
        item.id === UI.navigation.account || item.id === UI.navigation.contact
          ? `sidebar-${item.id}`
          : item.id,
      "aria-current": item.active ? ("page" as const) : undefined,
      title: collapsed ? item.label : undefined,
      className: cn(
        itemClass,
        "relative",
        child && !collapsed && "pl-6",
        collapsed && "justify-center px-0",
        item.active && activeClass,
      ),
      onClick: onNavigate,
    };
    const content = (
      <>
        <Icon name={item.icon} size="md" />
        <span className={collapsed ? "sr-only" : "min-w-0 flex-1"}>{item.label}</span>
      </>
    );
    return item.external ? (
      <a key={item.id} href={item.href} {...props}>
        {content}
      </a>
    ) : (
      <Link key={item.id} href={item.href} prefetch={false} {...props}>
        {content}
      </Link>
    );
  }
  return items.map((item) => {
    if (!item.children?.length) return link(item);
    const key = `${scope}:${item.id}`;
    const open = disclosures[key] ?? (item.active || item.children.some((child) => child.active));
    const toggle = () => {
      setDisclosures((current) => ({ ...current, [key]: !open }));
    };
    const label = t(open ? "collapseSection" : "expandSection", { section: item.label });
    if (collapsed)
      return (
        <DropdownMenu.Root key={item.id} modal={false}>
          <DropdownMenu.Trigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              data-ui={item.id}
              aria-label={item.label}
              title={item.label}
              data-active={item.active || item.children.some((child) => child.active)}
              className={cn(
                itemClass,
                "relative w-full justify-center px-0",
                (item.active || item.children.some((child) => child.active)) && activeClass,
              )}
            >
              <Icon name={item.icon} size="md" />
            </Button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              side="right"
              align="start"
              sideOffset={8}
              collisionPadding={12}
              aria-label={item.label}
              className="border-border bg-popover text-popover-foreground z-[70] max-h-[var(--radix-dropdown-menu-content-available-height)] max-w-[calc(100vw-1.5rem)] min-w-52 overflow-y-auto rounded-lg border p-1 shadow-md"
            >
              {(item.href ? [item, ...item.children] : item.children).map((child) => (
                <DropdownMenu.Item key={child.id} asChild>
                  <Link
                    href={child.href}
                    prefetch={false}
                    data-ui={child.id}
                    aria-current={child.active ? "page" : undefined}
                    className={cn(
                      itemClass,
                      "focus:bg-muted",
                      child.active && "text-primary font-medium",
                    )}
                    onClick={onNavigate}
                  >
                    <Icon name={child.icon} size="md" />
                    <span className="min-w-0 flex-1 break-words">{child.label}</span>
                  </Link>
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      );
    return (
      <div key={item.id} className="space-y-1">
        <div className="flex min-w-0 items-center">
          {item.href ? <div className="min-w-0 flex-1">{link(item)}</div> : null}
          <Button
            type="button"
            variant="ghost"
            size={item.href ? "icon" : "default"}
            aria-label={label}
            aria-expanded={open}
            aria-controls={`${scope}-${item.id}`}
            className={cn("h-11 shrink-0", !item.href && "w-full justify-start gap-3 px-3 text-sm")}
            onClick={toggle}
          >
            {!item.href ? (
              <>
                <Icon name={item.icon} size="md" />
                <span className="flex-1 text-left">{item.label}</span>
              </>
            ) : null}
            <Icon name={open ? "chevronUp" : "chevronDown"} size="sm" />
          </Button>
        </div>
        <div id={`${scope}-${item.id}`} hidden={!open} className="space-y-1">
          {item.children.map((child) => link(child, true))}
        </div>
      </div>
    );
  });
}

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
  const items: RailItem[] = corporate
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
  onShowMainNavigation?: () => void;
  onNavigate?: () => void;
};
export function ContextSidebar({
  corporate,
  pathname,
  items,
  scope,
  back,
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
            className={cn(itemClass, "w-full justify-start", isCollapsed && "justify-center px-0")}
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
            className={cn(itemClass, isCollapsed && "justify-center px-0")}
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
          className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2 py-4"
        >
          {contents(collapsed)}
        </nav>
      </aside>
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
              className="min-h-0 flex-1 space-y-2 overflow-y-auto"
            >
              {contents(false, true)}
            </nav>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
}
