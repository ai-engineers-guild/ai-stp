import { describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/api/http", () => ({ apiRequest: request }));
vi.mock("@/lib/api/corporate", () => ({
  readCorporateOrganization: () => Promise.resolve({ organization_id: "organization_1" }),
}));
vi.mock("@/lib/auth/require-session", () => ({
  sessionCookieValue: () => Promise.resolve("session"),
}));

import { GET } from "@/app/api/corporate/directory/route";

describe("corporate directory filter proxy", () => {
  it("forwards area and job title filters instead of silently dropping them", async () => {
    request.mockResolvedValue({ items: [], total: 0, facets: {} });
    const response = await GET(
      new NextRequest(
        "http://localhost/api/corporate/directory?resource=technologies&area_ids=area_1&job_title_ids=job_1",
      ),
    );
    expect(response.status).toBe(200);
    expect(request).toHaveBeenCalledWith(
      "/v1/corporate/organizations/organization_1/directory",
      expect.objectContaining({
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        query: expect.objectContaining({
          area_ids: ["area_1"],
          job_title_ids: ["job_1"],
          limit: 10,
        }),
      }),
    );
  });
});
