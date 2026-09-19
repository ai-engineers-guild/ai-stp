import { afterEach, expect, it, vi } from "vitest";
import { tryAsComponentId, tryAsSetupId } from "@/lib/brands";
import type { CorporateOverview, OrganizationListResponse } from "@/lib/api/generated/types.gen";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

it("resolves the populated corporate fixture through the organization discovery path", async () => {
  vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "corporate_hub");
  const { mockFetch } = await import("@/lib/api/mock-transport");
  const headers = { Authorization: "Bearer offline-test" };
  expect(mockFetch("GET", "/v1/organizations").status).toBe(401);
  const discovery = mockFetch("GET", "/v1/organizations", { headers });
  expect(discovery.status).toBe(200);
  const organizations = discovery.body as OrganizationListResponse;
  const corporate = organizations.items.find((item) => item.kind === "corporate");
  expect(corporate).toBeDefined();
  const overview = mockFetch(
    "GET",
    `/v1/corporate/organizations/${corporate?.organization_id}/overview`,
    { headers },
  );
  expect(overview.status).toBe(200);
  const graph = overview.body as CorporateOverview;
  expect(graph.nodes.length).toBeGreaterThan(0);
  expect(
    graph.nodes
      .flatMap((node) => node.assignments)
      .every((assignment) =>
        assignment.object_kind === "component"
          ? tryAsComponentId(assignment.stable_id)
          : tryAsSetupId(assignment.stable_id),
      ),
  ).toBe(true);
  expect(
    mockFetch("GET", `/v1/corporate/organizations/${corporate?.organization_id}/roles`, {
      headers,
    }).status,
  ).toBe(200);
  expect(
    mockFetch("GET", "/v1/organizations", {
      headers: { ...headers, "X-AI-STP-Context-Fixture": "empty" },
    }).body,
  ).toEqual({ schema_version: 1, items: [] });
});

it("keeps personal discovery unchanged in the SaaS profile", async () => {
  vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "public_saas");
  const { mockFetch } = await import("@/lib/api/mock-transport");
  const discovery = mockFetch("GET", "/v1/organizations", {
    headers: { Authorization: "Bearer offline-test" },
  });
  expect((discovery.body as OrganizationListResponse).items.map((item) => item.kind)).toEqual([
    "personal",
  ]);
});
