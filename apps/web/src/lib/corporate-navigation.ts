import type { IconName } from "@/theme/icons";
import { canViewCorporateAdministration, canViewCorporateSection } from "@/lib/corporate-hub";
import { CORPORATE_NAV_PAGES } from "@/lib/corporate-navigation-pages";
import type { CorporateNavContextId, CorporateNavPage } from "@/lib/corporate-navigation-pages";

export { CORPORATE_NAV_PAGES };
export type { CorporateNavContextId, CorporateNavPage };

/** Label key of a non-root context heading, in the `hub` namespace. */
export const CORPORATE_NAV_CONTEXT_LABELS: Record<
  Exclude<CorporateNavContextId, "root">,
  string
> = {
  organization: "organization",
  landscape: "landscape",
  administration: "administration",
};

export type CorporateNavItem = {
  id: string;
  href: string;
  /** Label key in the `hub` namespace. */
  label: string;
  icon: IconName;
  active: boolean;
};

export type CorporateNavResolved = {
  context: CorporateNavContextId;
  /** Page that owns the route; null for unowned corporate surfaces. */
  page: CorporateNavPage | null;
  /** Back link out of a non-root context; root has none. */
  back: { href: string; label: string } | null;
  items: CorporateNavItem[];
};

const LOCALE_PREFIX = /^\/(?:en|ru)(?:\/ai)?/;

/** Strip locale, `/ai` projection marker, query, and hash before matching. */
export function normalizeCorporatePath(pathname: string): string {
  const clean = pathname.split(/[?#]/, 1)[0] ?? "/";
  const stripped = clean.replace(LOCALE_PREFIX, "");
  return stripped === "" ? "/" : stripped;
}

function matches(page: CorporateNavPage, path: string): number | null {
  let best: number | null = null;
  for (const exact of page.exact) {
    if (path === exact) best = Math.max(best ?? 0, exact.length);
  }
  for (const prefix of page.prefixes) {
    if (path === prefix || path.startsWith(`${prefix}/`)) {
      best = Math.max(best ?? 0, prefix.length);
    }
  }
  return best;
}

/** The page owning `path` by longest match — alias and canonical resolve together. */
export function corporateNavPage(pathname: string): CorporateNavPage | null {
  const path = normalizeCorporatePath(pathname);
  let winner: CorporateNavPage | null = null;
  let best = -1;
  for (const page of CORPORATE_NAV_PAGES) {
    const length = matches(page, path);
    if (length !== null && length > best) {
      winner = page;
      best = length;
    }
  }
  return winner;
}

function visible(page: CorporateNavPage, capabilities: readonly string[]): boolean {
  if (page.administration) return canViewCorporateAdministration(capabilities);
  if (page.section) return canViewCorporateSection(page.section, capabilities);
  return true;
}

/** Resolve one context, one back link, and the rail items for a corporate path. */
export function resolveCorporateNav(
  pathname: string,
  capabilities: readonly string[],
): CorporateNavResolved {
  const page = corporateNavPage(pathname);
  const context = page?.context ?? "root";
  const rendered = page !== null && (context === "root" ? page.root : page.rail);
  const activeId = page?.activeAs === undefined ? (rendered ? page.id : null) : page.activeAs;
  const source = CORPORATE_NAV_PAGES.filter((item) =>
    context === "root" ? item.root : item.context === context && item.rail,
  );
  const items = source
    .filter((item) => visible(item, capabilities))
    .map((item) => ({
      id: item.id,
      href: item.href,
      label: context === "root" ? (item.rootLabel ?? item.label) : item.label,
      icon: item.icon,
      active: item.id === activeId,
    }));
  // A hidden active page owns the route but lights no rail item — fail closed.
  const active = items.some((item) => item.active);
  return {
    context,
    page,
    back:
      context === "root" || context === "administration"
        ? null
        : { href: "/corporate/overview", label: "backToHub" },
    items: active ? items : items.map((item) => ({ ...item, active: false })),
  };
}

/** Ids of every rail item the capabilities allow, for the navigation endpoint. */
export function corporateNavPageIds(capabilities: readonly string[]): string[] {
  return CORPORATE_NAV_PAGES.filter(
    (page) => (page.rail || page.root) && visible(page, capabilities),
  ).map((page) => page.id);
}

export type CorporateRailEntry = CorporateNavItem & {
  children?: CorporateNavItem[];
};

/** Presentation of the server's allowed IDs. It never infers authority from a URL. */
export function resolveCorporateRail(
  pathname: string,
  allowedPages: readonly string[],
  mainNavigation = false,
) {
  const page = corporateNavPage(pathname);
  const context =
    mainNavigation || (page?.context === "administration" && !allowedPages.includes(page.id))
      ? "root"
      : (page?.context ?? "root");
  const activeId = page?.activeAs === undefined ? page?.id : page.activeAs;
  const allowed = CORPORATE_NAV_PAGES.filter((item) => allowedPages.includes(item.id));
  const item = (entry: CorporateNavPage): CorporateNavItem => ({
    id: entry.id,
    href: entry.href,
    label: entry.label,
    icon: entry.icon,
    active: entry.id === activeId,
  });
  let entries: CorporateRailEntry[];
  if (context === "administration") {
    const groups = [
      ["peopleAndAccess", "team"],
      ["referenceData", "technology"],
      ["security", "lock"],
      ["organization", "setup"],
      ["audit", "list"],
    ] as const;
    entries = groups.flatMap(([id, icon]) => {
      const children = allowed.filter((entry) => entry.group === id && entry.rail).map(item);
      // Existing reference directories also have an administrative entry.
      if (id === "referenceData") {
        children.push(...allowed.filter((entry) => entry.id === "categories").map(item));
      }
      return children.length
        ? [{ id: `group-${id}`, label: id, icon, href: "", active: false, children }]
        : [];
    });
  } else {
    entries = allowed
      .filter((entry) => entry.root)
      .map((entry) => {
        const children =
          entry.context !== "root" && entry.context !== "administration"
            ? allowed
                .filter(
                  (child) =>
                    child.context === entry.context &&
                    child.rail &&
                    child.id !== "categories" &&
                    (child.id !== entry.id || entry.id === "landscape"),
                )
                .map(item)
            : [];
        return {
          ...item(entry),
          active: entry.id === activeId || (entry.administration && page?.administration) === true,
          label: entry.rootLabel ?? entry.label,
          ...(children.length ? { children } : {}),
        };
      });
  }
  const detail =
    !mainNavigation &&
    page?.rail &&
    page.context !== "administration" &&
    normalizeCorporatePath(pathname).startsWith(`${page.href}/`);
  return {
    context,
    entries,
    back:
      detail && page.href !== "/corporate/technology-scans"
        ? { href: page.href, label: page.label }
        : null,
  };
}
