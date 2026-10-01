import type { IconName } from "@/theme/icons";
import { canViewCorporateAdministration, canViewCorporateSection } from "@/lib/corporate-hub";

/**
 * Corporate contextual navigation (ADR-0219). One manifest owns every corporate
 * page identity, its parent context, route matching, labels, icons, and the
 * capability that gates it. The rail renders from this manifest, so active
 * state cannot be owned by two chrome surfaces at once.
 */
export type CorporateNavContextId = "root" | "organization" | "landscape" | "administration";

export type CorporateNavPage = {
  /** Stable page identity shared by the rail and the machine projection. */
  id: string;
  /** Context the rail enters while this page is active. */
  context: CorporateNavContextId;
  href: string;
  /** Label key in the `hub` message namespace. */
  label: string;
  /** Label key override when the page is rendered as a root-rail context entry. */
  rootLabel?: string;
  icon: IconName;
  /** Capability section checked through canViewCorporateSection. */
  section?: string;
  /** Requires canViewCorporateAdministration. */
  administration?: boolean;
  /** Rendered as an item inside its own context rail. */
  rail: boolean;
  /** Rendered in the root rail as a context entry. */
  root: boolean;
  /** Routes owned exactly; deeper paths do not match. */
  exact: readonly string[];
  /** Route prefixes owned by this page (segment boundary, deeper paths included). */
  prefixes: readonly string[];
  /** Rail item activated for this page; undefined = own id; null = none. */
  activeAs?: string | null;
  /** Disclosure section inside Administration. */
  group?: "peopleAndAccess" | "referenceData" | "security" | "organization" | "audit";
};

export const CORPORATE_NAV_PAGES: readonly CorporateNavPage[] = [
  {
    id: "overview",
    context: "root",
    href: "/corporate/overview",
    label: "overview",
    icon: "cards",
    root: true,
    rail: false,
    exact: ["/corporate", "/corporate/overview"],
    prefixes: [],
  },
  {
    id: "catalog",
    context: "root",
    href: "/corporate/catalog",
    label: "catalog",
    icon: "objects",
    root: true,
    rail: false,
    section: "components",
    exact: [],
    prefixes: ["/corporate/catalog", "/corporate/components"],
  },
  {
    id: "organization",
    context: "organization",
    href: "/corporate/organization",
    label: "organization",
    icon: "team",
    root: true,
    rail: true,
    exact: [],
    prefixes: ["/corporate/organization"],
  },
  {
    id: "landscape",
    context: "landscape",
    href: "/corporate/technology-landscape",
    label: "landscape",
    icon: "technology",
    root: true,
    rail: true,
    section: "technologies",
    exact: [],
    prefixes: ["/corporate/technology-landscape"],
  },
  {
    id: "administration",
    group: "peopleAndAccess",
    context: "administration",
    href: "/corporate/organization/admins",
    label: "membersAndInvitations",
    rootLabel: "administration",
    icon: "access",
    root: true,
    rail: true,
    administration: true,
    exact: [],
    prefixes: ["/corporate/organization/admins"],
  },

  // Organization context.
  {
    id: "employees",
    context: "organization",
    href: "/corporate/employees",
    label: "employees",
    icon: "user",
    root: false,
    rail: true,
    section: "employees",
    exact: [],
    prefixes: ["/corporate/employees", "/corporate/members", "/corporate/publishers"],
  },
  {
    id: "projects",
    context: "organization",
    href: "/corporate/projects",
    label: "projects",
    icon: "component",
    root: false,
    rail: true,
    section: "projects",
    exact: [],
    prefixes: ["/corporate/projects"],
  },
  {
    id: "teams",
    context: "organization",
    href: "/corporate/teams",
    label: "teams",
    icon: "team",
    root: false,
    rail: true,
    section: "teams",
    exact: [],
    prefixes: ["/corporate/teams"],
  },
  {
    id: "technologies",
    context: "organization",
    href: "/corporate/technologies",
    label: "technologies",
    icon: "technology",
    root: false,
    rail: true,
    section: "technologies",
    exact: [],
    prefixes: ["/corporate/technologies"],
  },
  {
    id: "reports",
    context: "organization",
    href: "/corporate/reports",
    label: "reports",
    icon: "list",
    root: false,
    rail: true,
    section: "reports",
    exact: [],
    prefixes: ["/corporate/reports", "/corporate/installations", "/corporate/usage"],
  },

  // Landscape context.
  {
    id: "categories",
    context: "landscape",
    href: "/corporate/categories",
    label: "categories",
    icon: "filter",
    root: false,
    rail: true,
    section: "categories",
    exact: [],
    prefixes: ["/corporate/categories"],
  },
  {
    id: "mappings",
    context: "landscape",
    href: "/corporate/technology-mappings",
    label: "mappings",
    icon: "link",
    root: false,
    rail: true,
    section: "mappings",
    exact: [],
    prefixes: ["/corporate/technology-mappings"],
  },

  // Administration context.
  {
    id: "accessMatrix",
    group: "peopleAndAccess",
    context: "administration",
    href: "/corporate/organization/admins/access",
    label: "accessModel",
    icon: "lock",
    root: false,
    rail: true,
    administration: true,
    exact: [],
    prefixes: ["/corporate/organization/admins/access"],
  },
  {
    id: "roles",
    group: "peopleAndAccess",
    context: "administration",
    href: "/corporate/organization/admins/roles",
    label: "roles",
    icon: "access",
    root: false,
    rail: true,
    administration: true,
    exact: [],
    prefixes: ["/corporate/organization/admins/roles"],
  },
  {
    id: "auditJournal",
    group: "audit",
    context: "administration",
    href: "/corporate/organization/admins/audit",
    label: "auditJournal",
    icon: "list",
    root: false,
    rail: true,
    administration: true,
    exact: [],
    prefixes: ["/corporate/organization/admins/audit"],
  },
  {
    id: "employeeAccess",
    group: "peopleAndAccess",
    context: "administration",
    href: "/corporate/organization/admins/employees",
    label: "employeeAccess",
    icon: "user",
    root: false,
    rail: true,
    administration: true,
    exact: [],
    prefixes: ["/corporate/organization/admins/employees"],
  },
  {
    id: "jobTitles",
    group: "referenceData",
    context: "administration",
    href: "/corporate/organization/admins/job-titles",
    label: "job_titles",
    icon: "flag",
    root: false,
    rail: true,
    administration: true,
    exact: [],
    prefixes: ["/corporate/organization/admins/job-titles"],
  },
  {
    id: "settings",
    group: "organization",
    context: "administration",
    href: "/corporate/organization/admins/settings",
    label: "settings",
    icon: "setup",
    root: false,
    rail: true,
    administration: true,
    exact: [],
    prefixes: ["/corporate/organization/admins/settings"],
  },
  {
    id: "security",
    group: "security",
    context: "administration",
    href: "/corporate/organization/admins/security",
    label: "security",
    icon: "lock",
    root: false,
    rail: true,
    administration: true,
    exact: [],
    prefixes: ["/corporate/organization/admins/security"],
  },
  {
    id: "roleDetail",
    context: "administration",
    href: "/corporate/organization/admins",
    label: "admins",
    icon: "access",
    root: false,
    rail: false,
    administration: true,
    exact: [],
    prefixes: ["/corporate/roles"],
    activeAs: "roles",
  },

  // Preserve the existing configurable dashboard destination.
  {
    id: "dashboard",
    context: "root",
    href: "/corporate/dashboard",
    label: "dashboard",
    icon: "controls",
    root: true,
    rail: false,
    exact: ["/corporate/dashboard"],
    prefixes: [],
  },
];

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
        children.push(
          ...allowed.filter((entry) => ["categories", "landscape"].includes(entry.id)).map(item),
        );
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
