import { describe, expect, it, vi } from "vitest";

const request = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/http", () => ({ privateApiRequest: request }));

import { landscapeFilters, readTechnologyLandscape } from "@/lib/api/technology";

describe("technology landscape boundary", () => {
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
