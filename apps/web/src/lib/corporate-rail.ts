import {
  CORPORATE_NAV_PAGES,
  corporateNavPage,
  normalizeCorporatePath,
  type CorporateNavItem,
  type CorporateNavPage,
} from "@/lib/corporate-navigation";

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
      // The technology landscape directory is also reachable from Reference data.
      if (id === "referenceData") {
        children.push(...allowed.filter((entry) => entry.id === "landscape").map(item));
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
          entry.id === entry.context &&
          entry.context !== "root" &&
          entry.context !== "administration"
            ? allowed
                .filter(
                  (child) => child.context === entry.context && child.rail && child.id !== entry.id,
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
    back: detail ? { href: page.href, label: page.label } : null,
  };
}
