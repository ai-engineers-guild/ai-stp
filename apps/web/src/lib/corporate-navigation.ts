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
  /** Any-of capability requirement on top of the administration gate. */
  capabilities?: readonly string[];
  /** Rendered as an item inside its own context rail. */
  rail: boolean;
  /** Rendered in the root rail as a context entry. */
  root: boolean;
  /** Routes owned exactly; deeper paths do not match. */
  exact?: readonly string[];
  /** Route prefixes owned by this page (segment boundary, deeper paths included). */
  prefixes: readonly string[];
  /** Rail item activated for this page; undefined = own id; null = none. */
  activeAs?: string | null;
  /** Disclosure section inside Administration; undefined renders a flat rail item. */
  group?: "peopleAndAccess" | "referenceData" | "security" | "audit";
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
    prefixes: ["/corporate/technology-landscape"],
  },
  // Reports renders as a root-rail entry before the pinned Administration
  // item; manifest order is rail order, so it must precede it.
  {
    id: "reports",
    context: "organization",
    href: "/corporate/reports",
    label: "reports",
    icon: "list",
    root: true,
    rail: true,
    section: "reports",
    prefixes: ["/corporate/reports", "/corporate/installations", "/corporate/usage"],
  },
  {
    id: "administration",
    group: "peopleAndAccess",
    context: "administration",
    href: "/corporate/admins/members",
    label: "members",
    rootLabel: "administration",
    icon: "access",
    root: true,
    rail: true,
    administration: true,
    prefixes: ["/corporate/admins/members"],
  },
  {
    id: "invitations",
    group: "peopleAndAccess",
    context: "administration",
    href: "/corporate/admins/invitations",
    label: "invitations",
    icon: "mail",
    root: false,
    rail: true,
    administration: true,
    prefixes: ["/corporate/admins/invitations"],
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
    prefixes: ["/corporate/technologies"],
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
    prefixes: ["/corporate/technology-mappings"],
  },

  // Administration context.
  {
    id: "accessMatrix",
    group: "peopleAndAccess",
    context: "administration",
    href: "/corporate/admins/access-model",
    label: "accessModel",
    icon: "lock",
    root: false,
    rail: true,
    administration: true,
    prefixes: ["/corporate/admins/access-model"],
  },
  {
    id: "roles",
    group: "peopleAndAccess",
    context: "administration",
    href: "/corporate/admins/roles",
    label: "roles",
    icon: "access",
    root: false,
    rail: true,
    administration: true,
    prefixes: ["/corporate/admins/roles"],
  },
  {
    id: "auditJournal",
    context: "administration",
    href: "/corporate/admins/audit",
    label: "auditJournal",
    icon: "list",
    root: false,
    rail: true,
    administration: true,
    capabilities: ["audit.list", "audit.export"],
    prefixes: ["/corporate/admins/audit"],
  },
  {
    id: "employeeAccess",
    group: "peopleAndAccess",
    context: "administration",
    href: "/corporate/admins/employee-access",
    label: "employeeAccess",
    icon: "user",
    root: false,
    rail: true,
    administration: true,
    prefixes: ["/corporate/admins/employee-access"],
  },
  {
    id: "jobTitles",
    group: "referenceData",
    context: "administration",
    href: "/corporate/admins/job-titles",
    label: "job_titles",
    icon: "flag",
    root: false,
    rail: true,
    administration: true,
    prefixes: ["/corporate/admins/job-titles"],
  },
  {
    id: "technologyCategories",
    group: "referenceData",
    context: "administration",
    href: "/corporate/admins/tech-categories",
    label: "categories",
    icon: "filter",
    root: false,
    rail: true,
    administration: true,
    section: "categories",
    prefixes: ["/corporate/admins/tech-categories"],
  },
  {
    id: "security",
    context: "administration",
    href: "/corporate/admins/security",
    label: "security",
    icon: "lock",
    root: false,
    rail: true,
    administration: true,
    capabilities: ["service_principal.list", "organization.manage"],
    prefixes: ["/corporate/admins/security"],
  },
  {
    id: "telemetry",
    context: "administration",
    href: "/corporate/admins/telemetry",
    label: "telemetry",
    icon: "technology",
    root: false,
    rail: true,
    administration: true,
    capabilities: ["telemetry.read", "telemetry.manage"],
    prefixes: ["/corporate/admins/telemetry"],
  },
  {
    id: "roleDetail",
    context: "administration",
    href: "/corporate/admins/members",
    label: "admins",
    icon: "access",
    root: false,
    rail: false,
    administration: true,
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
    root: false,
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
  for (const exact of page.exact ?? []) {
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

export function corporateNavPageVisible(
  page: CorporateNavPage,
  capabilities: readonly string[],
): boolean {
  if (page.administration) {
    if (!canViewCorporateAdministration(capabilities)) return false;
    return (
      page.capabilities === undefined ||
      page.capabilities.some((permission) => capabilities.includes(permission))
    );
  }
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
    .filter((item) => corporateNavPageVisible(item, capabilities))
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
    (page) => (page.rail || page.root) && corporateNavPageVisible(page, capabilities),
  ).map((page) => page.id);
}
