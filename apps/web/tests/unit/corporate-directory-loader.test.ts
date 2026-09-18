import { beforeEach, expect, it, vi } from "vitest";

const { request } = vi.hoisted(() => ({
  request: vi.fn<
    (
      path: string,
      options?: {
        query?: Record<string, string | number | boolean | readonly string[] | undefined>;
      },
    ) => unknown
  >(),
}));
vi.mock("@/lib/api/http", () => ({ apiRequest: request }));
import { readCorporateDirectory, readCorporateDirectoryPages } from "@/lib/api/corporate";

beforeEach(() => vi.clearAllMocks());

it.each(["teams", "projects", "members", "technologies"] as const)(
  "loads every authorized %s card without falling back to legacy lists",
  async (resource) => {
    const facets = { leads: [], teams: [], technologies: [] };
    request.mockImplementation((path, options) => {
      if (path === "/v1/organizations")
        return { items: [{ organization_id: "organization_fixture", kind: "corporate" }] };
      if (path.endsWith("/context"))
        return { organization: { organization_id: "organization_fixture" }, capabilities: [] };
      if (path.endsWith("/directory")) {
        expect(options?.query).not.toHaveProperty("state");
        expect(options?.query).toMatchObject({
          resource,
          include_archived: true,
          limit: 256,
        });
        return {
          organization: { organization_id: "organization_fixture" },
          resource,
          items: [{ id: options?.query?.offset === 0 ? "first" : "second", name: "Team" }],
          total: 2,
          facets,
        };
      }
      throw new Error(`Unexpected request ${path}`);
    });
    const directory = await readCorporateDirectory("session", resource);
    expect(directory?.items.map((item) => item.id)).toEqual(["first", "second"]);
    expect(directory).toMatchObject({ facets, total: 2, roles: null });
    expect(request.mock.calls.filter(([path]) => path.endsWith("/directory"))).toHaveLength(2);
  },
);

it("preserves multiselect query values and reports incomplete pagination as an error", async () => {
  request.mockResolvedValue({ items: [], total: 1 });
  await expect(
    readCorporateDirectoryPages("session", "organization_fixture", {
      resource: "projects",
      team_ids: ["team_a", "team_b"],
      query: null,
    }),
  ).rejects.toMatchObject({ code: "AI_STP_UNAVAILABLE" });
  expect(request).toHaveBeenCalledWith(expect.stringContaining("/directory"), {
    sessionToken: "session",
    query: {
      resource: "projects",
      team_ids: ["team_a", "team_b"],
      query: undefined,
      is_lead: undefined,
      offset: 0,
      limit: 256,
    },
  });
});
