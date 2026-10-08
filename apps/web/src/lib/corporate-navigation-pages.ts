import type { IconName } from "@/theme/icons";

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
    label: "technologyMap",
    rootLabel: "landscape",
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
    id: "scans",
    context: "landscape",
    href: "/corporate/technology-scans",
    label: "scans",
    icon: "list",
    root: false,
    rail: true,
    section: "scans",
    exact: [],
    prefixes: ["/corporate/technology-scans"],
  },
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
    id: "technologyAreas",
    group: "referenceData",
    context: "administration",
    href: "/corporate/organization/admins/technology-areas",
    label: "technologyAreas",
    icon: "technology",
    root: false,
    rail: true,
    administration: true,
    exact: [],
    prefixes: ["/corporate/organization/admins/technology-areas"],
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
