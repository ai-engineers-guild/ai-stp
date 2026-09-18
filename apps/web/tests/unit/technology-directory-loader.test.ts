import { beforeEach, describe, expect, it, vi } from "vitest";

const { request } = vi.hoisted(() => ({
  request: vi.fn<
    (
      path: string,
      options?: {
        sessionToken?: string;
        query?: Record<string, string | number | boolean | readonly string[] | undefined>;
      },
    ) => unknown
  >(),
}));
vi.mock("@/lib/api/http", () => ({ apiRequest: request, privateApiRequest: request }));

import { readTechnologyDirectory } from "@/lib/api/technology";

const organizationId = "organization_fixture";

beforeEach(() => vi.clearAllMocks());

describe("technology directory loader", () => {
  it("uses the authorized named directory and category dictionary", async () => {
    request.mockImplementation((path: string) => {
      if (path === "/v1/organizations")
        return { items: [{ organization_id: organizationId, kind: "corporate" }] };
      if (path.endsWith("/capabilities"))
        return {
          capabilities: ["technology.list", "category.list", "category.read"],
          authorization_revision: "opaque-revision",
        };
      if (path.endsWith("/directory"))
        return {
          organization: { organization_id: organizationId, authorization_revision: 3 },
          resource: "technologies",
          items: [{ id: "technology_01", name: "Runtime", state: "active" }],
          total: 1,
          facets: { categories: [], leads: [], projects: [], teams: [], technologies: [] },
        };
      if (path.endsWith("/technology-categories")) return { items: [] };
      throw new Error(`Unexpected request ${path}`);
    });

    const result = await readTechnologyDirectory("session");

    expect(result?.directory?.items.map((item) => item.name)).toEqual(["Runtime"]);
    expect(result?.categories?.items).toEqual([]);
    expect(request.mock.calls.map(([path]) => path)).not.toContain(
      `/v1/corporate/organizations/${organizationId}/technologies`,
    );
    const directoryCall = request.mock.calls.find(([path]) => path.endsWith("/directory"));
    if (!directoryCall) throw new Error("directory request is missing");
    expect(directoryCall[1]?.sessionToken).toBe("session");
    expect(directoryCall[1]?.query).toMatchObject({
      resource: "technologies",
      include_archived: true,
    });
  });

  it("does not request a directory when technology listing is denied", async () => {
    request.mockImplementation((path: string) => {
      if (path === "/v1/organizations")
        return { items: [{ organization_id: organizationId, kind: "corporate" }] };
      if (path.endsWith("/capabilities"))
        return { capabilities: [], authorization_revision: "opaque-revision" };
      throw new Error(`Unexpected request ${path}`);
    });

    const result = await readTechnologyDirectory("session");

    expect(result?.directory).toBeNull();
    expect(request.mock.calls.map(([path]) => path)).not.toContain(
      `/v1/corporate/organizations/${organizationId}/directory`,
    );
  });
});
