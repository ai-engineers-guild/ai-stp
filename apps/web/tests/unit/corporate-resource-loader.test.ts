import { beforeEach, expect, it, vi } from "vitest";
const { request } = vi.hoisted(() => ({
  request: vi.fn<(path: string, options?: { query?: Record<string, string> }) => unknown>(),
}));
vi.mock("@/lib/api/http", () => ({ apiRequest: request }));
import {
  readCorporateResource,
  readCorporateCatalogAssignments,
  readCorporateAudit,
  corporateAuditCursor,
  corporateAuditFilters,
  readCorporateMemberAccess,
} from "@/lib/api/corporate";
beforeEach(() => vi.clearAllMocks());
it.each([
  { capabilities: ["member.update", "role.list", "project.list", "team.list", "audit.list"] },
  { capabilities: ["member.read", "role.list"] },
])("loads member administration narrowly for $capabilities", async ({ capabilities }) => {
  request.mockImplementation((path) => {
    if (path === "/v1/organizations")
      return { items: [{ organization_id: "organization_fixture", kind: "corporate" }] };
    if (path.endsWith("/context"))
      return { organization: { organization_id: "organization_fixture" }, capabilities };
    if (path.endsWith("/members/account_alice"))
      return { account_id: "account_alice", display_name: "Alice" };
    if (path.endsWith("/roles")) return { items: [] };
    throw new Error(`Unexpected request ${path}`);
  });
  const result = await readCorporateMemberAccess("session", "account_alice");
  const canManage = capabilities.includes("member.update");
  expect(result !== null).toBe(canManage);
  expect(request.mock.calls.map(([path]) => path)).toEqual([
    "/v1/organizations",
    "/v1/corporate/organizations/organization_fixture/context",
    ...(canManage
      ? [
          "/v1/corporate/organizations/organization_fixture/members/account_alice",
          "/v1/corporate/organizations/organization_fixture/roles",
        ]
      : []),
  ]);
});
it("accepts only a canonical employee identifier as an audit filter", () => {
  const actor_account_id = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
  expect(corporateAuditFilters({ actor_account_id, organization_id: "other" })).toEqual({
    actor_account_id,
  });
  for (const value of ["", "other", [actor_account_id], "account_" + "I".repeat(26)])
    expect(corporateAuditFilters({ actor_account_id: value })).toEqual({});
});
it("passes only a complete valid journal cursor to the API", () => {
  const valid = { before_id: "23", before_created_at: "2026-09-13T10:00:00Z" };
  expect(corporateAuditCursor({ ...valid, organization_id: "other_tenant" })).toEqual(valid);
  for (const invalid of [
    { before_id: "23" },
    { ...valid, before_id: "0" },
    { ...valid, before_id: "9007199254740993" },
    { ...valid, before_id: ["23"] },
    { ...valid, before_created_at: "not-a-date" },
  ])
    expect(corporateAuditCursor(invalid)).toEqual({});
});

it.each([
  { capabilities: [] },
  { capabilities: ["member.list"] },
  { capabilities: ["audit.list"] },
  {
    capabilities: [
      "audit.list",
      "member.list",
      "role.list",
      "binding.list",
      "service_principal.list",
    ],
  },
])("loads only authorized journal data for $capabilities", async ({ capabilities }) => {
  request.mockImplementation((path) => {
    if (path === "/v1/organizations")
      return { items: [{ organization_id: "organization_fixture", kind: "corporate" }] };
    if (path.endsWith("/context"))
      return { organization: { organization_id: "organization_fixture" }, capabilities };
    if (path.endsWith("/audit"))
      return { items: [], next_before_created_at: null, next_before_id: null };
    if (path.endsWith("/members"))
      return { items: [{ account_id: "account_alice", display_name: "Alice" }] };
    throw new Error(`Unexpected request ${path}`);
  });
  const result = await readCorporateAudit("session");
  const paths = request.mock.calls.map(([path]) => path);
  expect(paths.some((path) => path.endsWith("/audit"))).toBe(capabilities.includes("audit.list"));
  expect(paths.some((path) => path.endsWith("/members"))).toBe(
    capabilities.includes("audit.list") && capabilities.includes("member.list"),
  );
  expect(result === null).toBe(!capabilities.includes("audit.list"));
  expect(paths.some((path) => /\/(roles|bindings|service-principals)$/.test(path))).toBe(false);
});

it("loads a team directly and never fetches administrative collections", async () => {
  request.mockImplementation((path: string) => {
    if (path === "/v1/organizations")
      return { items: [{ organization_id: "organization_fixture", kind: "corporate" }] };
    if (path.endsWith("/context"))
      return {
        organization: { organization_id: "organization_fixture" },
        capabilities: [
          "team.list",
          "member.list",
          "audit.list",
          "binding.list",
          "service_principal.list",
        ],
        teams: [],
      };
    if (path.endsWith("/teams/team_mobile"))
      return { team_id: "team_mobile", name: "Mobile", members: [] };
    if (path.endsWith("/teams"))
      return { items: [{ team_id: "team_mobile", name: "Mobile", members: [] }] };
    if (path.endsWith("/members")) return { items: [] };
    throw new Error(`Unexpected request ${path}`);
  });
  const result = await readCorporateResource("session_fixture", "teams", "team_mobile");
  expect(result?.team?.name).toBe("Mobile");
  expect(result?.context.teams[0]?.name).toBe("Mobile");
  expect(request.mock.calls.map((call) => call[0])).toEqual([
    "/v1/organizations",
    "/v1/corporate/organizations/organization_fixture/context",
    "/v1/corporate/organizations/organization_fixture/teams/team_mobile",
    "/v1/corporate/organizations/organization_fixture/teams",
    "/v1/corporate/organizations/organization_fixture/members",
  ]);
});

it("loads assignment revision history across pages without truncating it", async () => {
  request.mockImplementation((_path, options) => {
    const offset = Number(options?.query?.offset);
    return { items: [{ assignment_id: `assignment_${offset}` }], total: 2 };
  });
  const result = await readCorporateCatalogAssignments(
    "session",
    "organization_fixture",
    "team",
    "operation_mobile",
  );
  expect(result.items.map((item) => item.assignment_id)).toEqual(["assignment_0", "assignment_1"]);
  expect(request.mock.calls.map((call) => call[1]?.query)).toEqual([
    {
      subject_kind: "team",
      subject_id: "operation_mobile",
      include_retired: "true",
      offset: "0",
      limit: "256",
    },
    {
      subject_kind: "team",
      subject_id: "operation_mobile",
      include_retired: "true",
      offset: "1",
      limit: "256",
    },
  ]);
});
it("offers authorized organization projects rather than only the viewer's own projects", async () => {
  request.mockImplementation((path) => {
    if (path === "/v1/organizations")
      return { items: [{ organization_id: "organization_fixture", kind: "corporate" }] };
    if (path.endsWith("/context"))
      return {
        organization: { organization_id: "organization_fixture" },
        capabilities: [
          "project.list",
          "role.list",
          "audit.list",
          "binding.list",
          "service_principal.list",
        ],
        projects: [],
        teams: [],
      };
    if (path.endsWith("/members/account_alice"))
      return { account_id: "account_alice", display_name: "Alice" };
    if (path.endsWith("/members/account_alice/projects")) return { items: [] };
    if (path.endsWith("/projects"))
      return { items: [{ project_id: "remote_project_mobile", name: "Mobile app" }] };
    throw new Error(`Unexpected request ${path}`);
  });
  const result = await readCorporateResource("session", "members", "account_alice");
  expect(result?.context.projects).toEqual([
    { project_id: "remote_project_mobile", name: "Mobile app" },
  ]);
  expect(result?.projectMemberships?.items).toEqual([]);
  expect(request.mock.calls.some(([path]) => path.endsWith("/roles"))).toBe(false);
});
