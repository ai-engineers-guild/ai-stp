import { beforeEach, expect, it, vi } from "vitest";
import { loadCorporateGrantDialog } from "@/actions/entity-actions";

const mocks = vi.hoisted(() => ({
  session: vi.fn(),
  csrf: vi.fn(),
  organization: vi.fn(),
  workspace: vi.fn(),
  memberAccess: vi.fn(),
  technologies: vi.fn(),
  catalog: vi.fn(),
  categories: vi.fn(),
  api: vi.fn(),
}));
vi.mock("@/lib/auth/require-session", () => ({ sessionCookieValue: mocks.session }));
vi.mock("@/lib/auth/session", () => ({ readCsrfToken: mocks.csrf }));
vi.mock("@/lib/api/http", () => ({ apiRequest: mocks.api }));
vi.mock("@/lib/api/corporate", () => ({
  readCorporateOrganization: mocks.organization,
  readCorporateWorkspace: mocks.workspace,
  readCorporateMemberAccess: mocks.memberAccess,
  readCorporateScopeTechnologies: mocks.technologies,
  readCorporateCatalogScopeOptions: mocks.catalog,
  readCorporateCategoryScopeOptions: mocks.categories,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.session.mockResolvedValue("session");
  mocks.csrf.mockResolvedValue("csrf");
  mocks.api.mockImplementation((path: string) => {
    if (path === "/v1/entity-actions/query")
      return Promise.resolve({ items: [{ actions: [{ id: "manage_access" }] }] });
    return Promise.reject(new Error("optional matrix unavailable"));
  });
  mocks.workspace.mockResolvedValue({
    organization: { organization_id: "org" },
    context: {
      organization: { authorization_revision: 7 },
      capabilities: ["binding.create", "member.read", "member.list", "role.read"],
      teams: [],
      projects: [],
    },
    members: { items: [{ account_id: "employee" }] },
    roles: { items: [] },
  });
  mocks.memberAccess.mockRejectedValue(new Error("optional access unavailable"));
  mocks.technologies.mockRejectedValue(new Error("optional technologies unavailable"));
  mocks.catalog.mockRejectedValue(new Error("optional catalog unavailable"));
  mocks.categories.mockRejectedValue(new Error("optional categories unavailable"));
});

it("opens a member grant with the selected employee when optional scope sources fail", async () => {
  const result = await loadCorporateGrantDialog({
    kind: "member",
    id: "employee",
    organization_id: "org",
  });
  expect(result.initialMemberIds).toEqual(["employee"]);
  expect(result.organizationId).toBe("org");
  expect(result.authorizationRevision).toBe(7);
  expect(result.scopeOptions).toEqual([]);
  expect(result.definitions).toEqual([]);
});

it("does not load grant form data when the server omits manage_access", async () => {
  mocks.api.mockResolvedValue({ items: [{ actions: [] }] });
  await expect(
    loadCorporateGrantDialog({
      kind: "member",
      id: "employee",
      organization_id: "org",
    }),
  ).rejects.toThrow("grant unavailable");
  expect(mocks.workspace).not.toHaveBeenCalled();
});

it("keeps the requested component scope when the catalog list is unavailable", async () => {
  const result = await loadCorporateGrantDialog({
    kind: "component",
    id: "component_1",
    organization_id: "org",
  });
  expect(result.initialScope).toBe("catalog_object:component_1");
  expect(result.scopeOptions).toEqual([
    { value: "catalog_object:component_1", label: "component_1" },
  ]);
});
