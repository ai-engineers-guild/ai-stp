import { describe, expect, it } from "vitest";

import {
  corporateNavPage,
  corporateNavPageIds,
  normalizeCorporatePath,
  resolveCorporateNav,
  resolveCorporateRail,
} from "@/lib/corporate-navigation";

const MEMBER = ["member.list"];
const REPORTER = ["telemetry.read"];
const ADMIN = ["role.read"];

describe("normalizeCorporatePath", () => {
  it("strips locale, /ai marker, query, and hash", () => {
    expect(normalizeCorporatePath("/en/corporate/teams/team_1?x=1#y")).toBe(
      "/corporate/teams/team_1",
    );
    expect(normalizeCorporatePath("/ru/ai/corporate/catalog")).toBe("/corporate/catalog");
    expect(normalizeCorporatePath("/corporate")).toBe("/corporate");
  });
});

describe("corporateNavPage", () => {
  it("resolves one canonical page per route, including aliases and details", () => {
    const cases: Array<[string, string | null]> = [
      ["/corporate", "overview"],
      ["/corporate/overview", "overview"],
      ["/corporate/catalog", "catalog"],
      ["/corporate/catalog/components/comp_x", "catalog"],
      ["/corporate/components", "catalog"],
      ["/corporate/organization", "organization"],
      ["/corporate/employees", "employees"],
      ["/corporate/employees/new", "employees"],
      ["/corporate/members", "employees"],
      ["/corporate/teams/team_x", "teams"],
      ["/corporate/projects", "projects"],
      ["/corporate/technologies/t_1/edit", "technologies"],
      ["/corporate/reports/heartbeat", "reports"],
      ["/corporate/installations", "reports"],
      ["/corporate/technology-landscape", "landscape"],
      ["/corporate/technology-scans", "scans"],
      ["/corporate/technology-scans/scan_1", "scans"],
      ["/corporate/categories/cat_1", "categories"],
      ["/corporate/technology-mappings", "mappings"],
      ["/corporate/organization/admins", "administration"],
      ["/corporate/organization/admins/access", "accessMatrix"],
      ["/corporate/organization/admins/audit", "auditJournal"],
      ["/corporate/organization/admins/employees/account_1", "employeeAccess"],
      ["/corporate/organization/admins/job-titles", "jobTitles"],
      ["/corporate/organization/admins/technology-areas", "technologyAreas"],
      ["/corporate/organization/admins/settings", "settings"],
      ["/corporate/roles/role_1", "roleDetail"],
      ["/corporate/dashboard", "dashboard"],
      ["/corporate/account", null],
      ["/corporate/devices", null],
    ];
    for (const [path, id] of cases) {
      expect(corporateNavPage(path)?.id ?? null, path).toBe(id);
    }
  });

  it("keeps administration pages out of the organization index prefix", () => {
    // /corporate/organization/admins must not be claimed by the organization page.
    expect(corporateNavPage("/corporate/organization/admins")?.context).toBe("administration");
  });
});

describe("resolveCorporateNav", () => {
  it("marks overview active on the hub index without a back link", () => {
    const nav = resolveCorporateNav("/corporate", [...ADMIN, ...MEMBER, "technology.list"]);
    expect(nav.context).toBe("root");
    expect(nav.back).toBeNull();
    expect(nav.items.map((item) => item.id)).toEqual([
      "overview",
      "catalog",
      "organization",
      "landscape",
      "administration",
      "dashboard",
    ]);
    expect(nav.items.find((item) => item.active)?.id).toBe("overview");
  });

  it("enters the organization context with a back link and one active item", () => {
    const nav = resolveCorporateNav("/en/corporate/teams/team_1", [...MEMBER, "team.list"]);
    expect(nav.context).toBe("organization");
    expect(nav.back).toEqual({ href: "/corporate/overview", label: "backToHub" });
    expect(nav.items.filter((item) => item.active).map((item) => item.id)).toEqual(["teams"]);
  });

  it("enters the administration context and lights the index on nested pages", () => {
    const nav = resolveCorporateNav("/corporate/organization/admins/access", ADMIN);
    expect(nav.context).toBe("administration");
    expect(nav.back).toBeNull();
    expect(nav.items.map((item) => item.id)).toEqual([
      "administration",
      "accessMatrix",
      "roles",
      "auditJournal",
      "employeeAccess",
      "technologyAreas",
      "jobTitles",
      "settings",
      "security",
    ]);
    expect(nav.items.find((item) => item.active)?.id).toBe("accessMatrix");
  });

  it("lights the administration index for the employee-access route", () => {
    const nav = resolveCorporateNav("/corporate/organization/admins/employees/account_1", ADMIN);
    expect(nav.items.find((item) => item.active)?.id).toBe("employeeAccess");
  });

  it("lights the roles item for the role detail route", () => {
    const nav = resolveCorporateNav("/corporate/roles/role_1", ADMIN);
    expect(nav.items.find((item) => item.active)?.id).toBe("roles");
  });

  it("fails closed: administration stays hidden without admin capabilities", () => {
    const nav = resolveCorporateNav("/corporate", MEMBER);
    expect(nav.items.map((item) => item.id)).not.toContain("administration");
    // Being on an admin URL without the capability lights nothing.
    const denied = resolveCorporateNav("/corporate/organization/admins/access", MEMBER);
    expect(denied.items.every((item) => !item.active)).toBe(true);
  });

  it("fails closed on unknown capability values", () => {
    const nav = resolveCorporateNav("/corporate/organization/admins", ["nonsense.value"]);
    expect(nav.items).toHaveLength(0);
  });

  it("keeps dashboard reachable with its own active rail item", () => {
    const nav = resolveCorporateNav("/corporate/dashboard", ADMIN);
    expect(nav.context).toBe("root");
    expect(nav.page?.id).toBe("dashboard");
    expect(nav.items.filter((item) => item.active).map((item) => item.id)).toEqual(["dashboard"]);
  });

  it("filters organization children by capability sections", () => {
    const nav = resolveCorporateNav("/corporate/organization", [...MEMBER, ...REPORTER]);
    const ids = nav.items.map((item) => item.id);
    expect(ids).toEqual(["organization", "employees", "reports"]);
    // member.list also satisfies the catalog section on the root rail.
    expect(resolveCorporateNav("/corporate", MEMBER).items.map((item) => item.id)).toContain(
      "catalog",
    );
  });
});

describe("corporateNavPageIds", () => {
  it("lists only pages the capabilities allow", () => {
    expect(corporateNavPageIds([])).toEqual(["overview", "organization", "dashboard"]);
    expect(corporateNavPageIds(ADMIN)).toContain("administration");
    expect(corporateNavPageIds(ADMIN)).toContain("auditJournal");
    expect(corporateNavPageIds(ADMIN)).toContain("employeeAccess");
  });
});

it.each([
  "/en/corporate/organization/admins",
  "/ru/corporate/organization/admins/access",
  "/corporate/organization/admins/employees/account_1",
  "/corporate/roles/role_1",
])("keeps authorized root navigation on a denied administration route: %s", (pathname) => {
  const allowed = ["overview", "catalog", "organization", "dashboard"];
  const rail = resolveCorporateRail(pathname, allowed);
  expect(rail.context).toBe("root");
  expect(rail.entries.map((entry) => entry.id)).toEqual(allowed);
  expect(rail.entries.some((entry) => entry.active)).toBe(false);
  expect(rail.back).toBeNull();
  expect(resolveCorporateRail(pathname, []).entries).toEqual([]);
});
