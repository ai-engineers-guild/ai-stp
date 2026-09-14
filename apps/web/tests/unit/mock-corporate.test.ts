import { randomUUID } from "node:crypto";
import { expect, it } from "vitest";
import { corporateHandlers } from "@/lib/api/mock-corporate";
import { mockFetch } from "@/lib/api/mock-transport";
import { entityProfileViewSchema } from "@/lib/corporate-detail";

it("offline corporate profiles persist once, reject stale writes and require mock presence", () => {
  const path =
    "/v1/corporate/organizations/organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z/entity-profiles/team/operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
  expect(corporateHandlers("GET", path, false, undefined)?.status).toBe(401);
  const before = entityProfileViewSchema.parse(
    corporateHandlers("GET", path, true, undefined)?.body,
  );
  const body = {
    schema_version: 1,
    fields: { ...before.fields, description: "**Saved offline fixture**" },
    expected_revision: before.revision,
    authorization_revision: 1,
    idempotency_key: randomUUID(),
  };
  expect(corporateHandlers("PATCH", path, true, body)?.status).toBe(405);
  const first = corporateHandlers("PUT", path, true, body);
  expect(first?.status).toBe(200);
  expect(corporateHandlers("PUT", path, true, body)).toEqual(first);
  const after = entityProfileViewSchema.parse(
    corporateHandlers("GET", path, true, undefined)?.body,
  );
  expect(after.revision).toBe(before.revision + 1);
  expect(after.fields.description).toBe(body.fields.description);
  expect(
    corporateHandlers("PUT", path, true, { ...body, idempotency_key: randomUUID() })?.status,
  ).toBe(409);
  expect(corporateHandlers("PUT", path, true, { ...body, authorization_revision: 2 })?.status).toBe(
    422,
  );
  expect(
    corporateHandlers("GET", path.replace("operation_", "missing_"), true, undefined)?.status,
  ).toBe(404);
  expect(corporateHandlers("GET", "/v1/catalog", true, undefined)).toBeNull();
});

it("dispatches corporate profile reads through the existing mock transport", () => {
  const path =
    "/v1/corporate/organizations/organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z/entity-profiles/team/operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
  expect(mockFetch("GET", path).status).toBe(401);
  const result = mockFetch("GET", path, { headers: { Authorization: "Bearer offline-test" } });
  expect(result.status).toBe(200);
  expect(entityProfileViewSchema.safeParse(result.body).success).toBe(true);
});

it("keeps the technology profile owner aligned with the directory employee", () => {
  const path =
    "/v1/corporate/organizations/organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z/entity-profiles/technology/technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
  expect(corporateHandlers("GET", path, true, undefined)?.body).toMatchObject({
    owner_account_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  });
});

it("rejects unknown directory resources without trusting a cast", () => {
  const path = "/v1/corporate/organizations/organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z/directory";
  expect(
    corporateHandlers("GET", path, true, undefined, new URLSearchParams({ resource: "invalid" }))
      ?.status,
  ).toBe(422);
});

it("dispatches current project relations from the canonical corporate fixture", () => {
  const organizationId = "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
  const projectId = "remote_project_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
  const teamId = "operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
  const technologyId = "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
  const base = `/v1/corporate/organizations/${organizationId}`;
  const teams = corporateHandlers("GET", `${base}/projects/${projectId}/teams`, true, undefined);
  const reverseProjects = corporateHandlers(
    "GET",
    `${base}/teams/${teamId}/projects`,
    true,
    undefined,
  );
  const technologies = corporateHandlers(
    "GET",
    `${base}/projects/${projectId}/technologies`,
    true,
    undefined,
  );
  expect(teams?.body).toMatchObject({
    items: [
      {
        organization_id: organizationId,
        project_id: projectId,
        role: "owner",
        state: "current",
        team_id: teamId,
      },
    ],
    total: 1,
  });
  expect(reverseProjects?.body).toMatchObject({
    items: [{ organization_id: organizationId, project_id: projectId, team_id: teamId }],
    total: 1,
  });
  expect(technologies?.body).toMatchObject({
    items: [
      {
        organization_id: organizationId,
        project_id: projectId,
        state: "current",
        technology_id: technologyId,
      },
    ],
    total: 1,
  });
  expect(
    corporateHandlers("GET", `${base}/projects/${projectId}/teams`, false, undefined)?.status,
  ).toBe(401);
});

it("dispatches the current reverse technology project relation", () => {
  const organizationId = "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
  const projectId = "remote_project_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
  const technologyId = "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
  const base = `/v1/corporate/organizations/${organizationId}`;
  const path = `${base}/technologies/${technologyId}/projects`;
  expect(corporateHandlers("GET", path, true, undefined)?.body).toMatchObject({
    items: [
      {
        organization_id: organizationId,
        project_id: projectId,
        state: "current",
        technology_id: technologyId,
      },
    ],
    total: 1,
  });
  expect(corporateHandlers("GET", path, false, undefined)?.status).toBe(401);
});
