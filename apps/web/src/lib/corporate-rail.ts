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

const ADMIN_GROUP_ICONS = {
  peopleAndAccess: "team",
  referenceData: "technology",
  security: "lock",
  audit: "list",
} as const;

/** Administration rail: flat items plus disclosure groups, single-child groups hoisted. */
function administrationEntries(
  allowed: readonly CorporateNavPage[],
  item: (entry: CorporateNavPage) => CorporateNavItem,
): CorporateRailEntry[] {
  // The server list covers every corporate context; this rail owns only the
  // administration pages plus the explicit landscape cross-link below.
  const administration = allowed.filter((entry) => entry.context === "administration");
  const children = new Map<NonNullable<CorporateNavPage["group"]>, CorporateNavItem[]>();
  for (const entry of administration) {
    if (!entry.rail || !entry.group) continue;
    const bucket = children.get(entry.group) ?? [];
    bucket.push(item(entry));
    children.set(entry.group, bucket);
  }
  // The technology landscape directory is also reachable from Reference data.
  children
    .get("referenceData")
    ?.push(...allowed.filter((entry) => entry.id === "landscape").map(item));
  const entries: CorporateRailEntry[] = [];
  const emitted = new Set<string>();
  for (const entry of administration) {
    if (!entry.rail) continue;
    if (!entry.group) {
      entries.push(item(entry));
      continue;
    }
    if (emitted.has(entry.group)) continue;
    emitted.add(entry.group);
    const bucket = children.get(entry.group) ?? [];
    const [only] = bucket;
    // A disclosure with one child reads as noise; hoist it flat.
    entries.push(
      bucket.length === 1 && only
        ? only
        : {
            id: `group-${entry.group}`,
            label: entry.group,
            icon: ADMIN_GROUP_ICONS[entry.group],
            href: "",
            active: false,
            children: bucket,
          },
    );
  }
  return entries;
}

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
    entries = administrationEntries(allowed, item);
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
                  (child) =>
                    child.context === entry.context &&
                    child.rail &&
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
