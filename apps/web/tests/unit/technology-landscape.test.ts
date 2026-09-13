import { describe, expect, it, vi } from "vitest";

const request = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/http", () => ({ privateApiRequest: request }));

import {
  landscapeFilters,
  readTechnologyLandscape,
  readTechnologyRegistry,
  readTechnologyCapabilities,
  readTechnologyDetail,
  readProjectTechnologyDetail,
  readTeamProjects,
  readTechnologyProjects,
} from "@/lib/api/technology";

describe("technology landscape boundary", () => {
  it("resolves related team names without requiring the whole team directory", async () => {
    request.mockReset();
    request.mockResolvedValueOnce({
      capabilities: ["technology.read", "technology_team.list", "technology_team.read"],
      authorization_revision: "opaque",
    });
    request.mockResolvedValueOnce({ technology_id: "technology-known" });
    request.mockResolvedValueOnce({
      items: [{ team_id: "operation-mobile", state: "current" }],
      total: 1,
    });
    request.mockResolvedValueOnce({ team_id: "operation-mobile", name: "Mobile" });
    const detail = await readTechnologyDetail(
      "session",
      "organization-explicit",
      "technology-known",
    );
    expect(detail?.availableTeams[0]?.name).toBe("Mobile");
    expect(request).toHaveBeenLastCalledWith(
      "/v1/corporate/organizations/organization-explicit/teams/operation-mobile",
      { sessionToken: "session" },
    );
    expect(request).toHaveBeenCalledTimes(4);
  });

  it("does not turn technology-scoped team discovery into organization discovery", async () => {
    request.mockReset();
    request.mockResolvedValueOnce({
      capabilities: ["technology.read", "team.list"],
      authorization_revision: "opaque",
    });
    request.mockResolvedValueOnce({ capabilities: [], authorization_revision: "opaque" });
    request.mockResolvedValueOnce({ technology_id: "technology-known" });
    const detail = await readTechnologyDetail(
      "session",
      "organization-explicit",
      "technology-known",
    );
    expect(detail?.availableTeams).toEqual([]);
    expect(request).toHaveBeenCalledTimes(3);
  });
  it("reads all reverse technology links and only their authorized project details", async () => {
    request.mockReset();
    request.mockResolvedValueOnce({ items: [{ project_id: "project-first" }], total: 2 });
    request.mockResolvedValueOnce({ items: [{ project_id: "project-second" }], total: 2 });
    request.mockResolvedValueOnce({ project_id: "project-first", name: "First" });
    request.mockResolvedValueOnce({ project_id: "project-second", name: "Second" });
    const result = await readTechnologyProjects(
      "session",
      "organization-explicit",
      "technology-known",
    );
    expect(result.status).toBe("data");
    if (result.status !== "data") throw new Error("projection unavailable");
    expect(result.data.projects.map((item) => item.name)).toEqual(["First", "Second"]);
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/v1/corporate/organizations/organization-explicit/technologies/technology-known/projects",
      { sessionToken: "session", query: { offset: "1", limit: "256" } },
    );
    expect(request.mock.calls.map((call) => call[0] as string)).not.toContain(
      "/v1/corporate/organizations/organization-explicit/projects",
    );
  });

  it("keeps failed reverse reads distinct from an empty related-project list", async () => {
    request.mockReset();
    request.mockRejectedValueOnce(new Error("offline"));
    const result = await readTechnologyProjects(
      "session",
      "organization-explicit",
      "technology-known",
    );
    expect(result.status).toBe("error");
    expect(request).toHaveBeenCalledTimes(1);
  });
  it("reads reverse project links under the explicit team scope", async () => {
    request.mockReset();
    request.mockResolvedValueOnce({
      capabilities: ["project_team.list", "project_team.read", "project.list"],
      authorization_revision: "opaque",
    });
    request.mockResolvedValueOnce({
      items: [{ project_id: "mobile-project", team_id: "mobile-team", state: "current" }],
    });
    request.mockResolvedValueOnce({
      items: [{ project_id: "mobile-project", name: "Mobile application" }],
    });
    const detail = await readTeamProjects("opaque-session", "organization-explicit", "mobile-team");
    expect(detail?.projects?.items[0]?.name).toBe("Mobile application");
    expect(request).toHaveBeenNthCalledWith(
      1,
      "/v1/organizations/organization-explicit/capabilities",
      { sessionToken: "opaque-session", query: { scope_kind: "team", scope_id: "mobile-team" } },
    );
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/v1/corporate/organizations/organization-explicit/teams/mobile-team/projects",
      { sessionToken: "opaque-session" },
    );
  });
  it("reads a known project without project list or relationship discovery permissions", async () => {
    request.mockReset();
    request.mockResolvedValueOnce({
      capabilities: ["project.read"],
      authorization_revision: "opaque",
    });
    request.mockResolvedValueOnce({ project_id: "known-project" });
    const detail = await readProjectTechnologyDetail(
      "opaque-session",
      "organization-explicit",
      "known-project",
    );
    expect(detail?.relations).toBeNull();
    expect(request).toHaveBeenCalledTimes(2);
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/v1/corporate/organizations/organization-explicit/projects/known-project",
      { sessionToken: "opaque-session" },
    );
  });
  it("reads a known technology without requiring list or speculating about category discovery", async () => {
    request.mockReset();
    request.mockResolvedValueOnce({
      capabilities: ["technology.read"],
      authorization_revision: "opaque",
    });
    request.mockResolvedValueOnce({ technology_id: "known-technology" });
    const detail = await readTechnologyDetail(
      "opaque-session",
      "organization-explicit",
      "known-technology",
    );
    expect(detail?.categories).toBeNull();
    expect(request).toHaveBeenCalledTimes(2);
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/v1/corporate/organizations/organization-explicit/technologies/known-technology",
      { sessionToken: "opaque-session" },
    );
  });
  it("reads governed technology projections from their canonical endpoints", async () => {
    request.mockReset();
    request.mockResolvedValueOnce({
      capabilities: [
        "technology.read",
        "technology_decision.read",
        "technology_team.list",
        "technology_team.read",
      ],
      authorization_revision: "opaque",
    });
    request.mockResolvedValueOnce({ technology_id: "known-technology" });
    request.mockResolvedValueOnce({
      technology_id: "known-technology",
      revision: 1,
      lead_account_id: null,
      approved: false,
      adoption: "none",
    });
    request.mockResolvedValueOnce({ items: [], total: 0 });
    const detail = await readTechnologyDetail(
      "opaque-session",
      "organization-explicit",
      "known-technology",
    );
    expect(detail?.decision?.status).toBe("data");
    expect(detail?.teams?.status).toBe("data");
    expect(request).toHaveBeenNthCalledWith(
      3,
      "/v1/corporate/organizations/organization-explicit/technologies/known-technology/decision",
      { sessionToken: "opaque-session" },
    );
    expect(request).toHaveBeenNthCalledWith(
      4,
      "/v1/corporate/organizations/organization-explicit/technologies/known-technology/responsible-teams?include_history=true",
      { sessionToken: "opaque-session" },
    );
  });
  it("does not speculate about registry reads without the independent capabilities", async () => {
    request.mockReset();
    request.mockResolvedValueOnce({
      capabilities: ["category.list"],
      authorization_revision: "opaque",
    });
    const registry = await readTechnologyRegistry("opaque-session", "organization-explicit");
    expect(registry.categories).toBeNull();
    expect(registry.technologies).toBeNull();
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("does not use a technology-scoped dictionary grant for organization discovery", async () => {
    request.mockReset();
    request.mockResolvedValueOnce({
      capabilities: ["technology.read", "category.list", "category.read"],
      authorization_revision: "opaque",
    });
    request.mockResolvedValueOnce({ capabilities: [], authorization_revision: "opaque" });
    request.mockResolvedValueOnce({ technology_id: "known-technology" });
    const detail = await readTechnologyDetail(
      "opaque-session",
      "organization-explicit",
      "known-technology",
    );
    expect(detail?.categories).toBeNull();
    expect(detail?.technology.technology_id).toBe("known-technology");
    expect(request).toHaveBeenCalledTimes(3);
    expect(request).toHaveBeenNthCalledWith(
      2,
      "/v1/organizations/organization-explicit/capabilities",
      { sessionToken: "opaque-session" },
    );
  });

  it("requests known resource scopes without selecting a mode", async () => {
    request.mockReset();
    request.mockResolvedValueOnce({ capabilities: [] });
    await readTechnologyCapabilities("opaque-session", "organization-explicit", {
      kind: "project",
      id: "known-project",
    });
    expect(request).toHaveBeenCalledWith("/v1/organizations/organization-explicit/capabilities", {
      sessionToken: "opaque-session",
      query: { scope_kind: "project", scope_id: "known-project" },
    });
  });
  it("preserves supported filters but never forwards unknown parameters or repeated values", () => {
    expect(
      landscapeFilters({
        context: "production",
        include_inactive: "true",
        offset: "128",
        project_offset: "256",
        category_id: "",
        view: "radar",
        sessionToken: "must-not-forward",
        team_id: ["first", "second"],
      }),
    ).toEqual({
      context: "production",
      include_inactive: "true",
      offset: "128",
      project_offset: "256",
      view: "radar",
    });
  });

  it("uses the private request boundary and the explicit organization for each call", async () => {
    request.mockResolvedValueOnce({ items: [], total: 0 });
    const filters = { project_id: "project-explicit", review: "confirmed" };
    await readTechnologyLandscape("opaque-session", "organization-explicit", filters);
    expect(request).toHaveBeenCalledWith(
      "/v1/corporate/organizations/organization-explicit/technology-landscape",
      { sessionToken: "opaque-session", query: filters },
    );
  });
});
