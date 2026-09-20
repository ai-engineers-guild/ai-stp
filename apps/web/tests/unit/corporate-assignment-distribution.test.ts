import { beforeEach, expect, it, vi } from "vitest";

const { request } = vi.hoisted(() => ({
  request: vi.fn<
    (
      path: string,
      options?: {
        method?: string;
        query?: Record<string, string | number | boolean | readonly string[] | undefined>;
        body?: unknown;
      },
    ) => unknown
  >(),
}));
vi.mock("@/lib/api/http", () => ({ apiRequest: request }));
import {
  distributeCorporateAssignment,
  planCorporateAssignment,
  readCorporateAssignmentDistribution,
} from "@/lib/api/corporate";

const organizationId = "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const sourceId = "operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z";

beforeEach(() => vi.clearAllMocks());

it("posts the distribution request to the shared contract route", async () => {
  request.mockImplementation((path, options) => {
    expect(path).toBe(
      `/v1/corporate/organizations/${organizationId}/catalog-assignments/distribution`,
    );
    expect(options?.method).toBe("POST");
    expect(options?.body).toMatchObject({
      source_assignment_id: sourceId,
      action: "assign",
      dry_run: true,
      expected_revision: 1,
    });
    return {
      schema_version: 1,
      distribution_id: null,
      organization_id: organizationId,
      source_assignment_id: sourceId,
      action: "assign",
      dry_run: true,
      source_revision: 1,
      targets: [],
      exclusions: [],
      counts: { applied: 0, skipped: 0, conflicted: 0, denied: 0, failed: 0 },
    };
  });
  const result = await distributeCorporateAssignment("session", organizationId, {
    schema_version: 1,
    source_assignment_id: sourceId,
    action: "assign",
    dry_run: true,
    expected_revision: 1,
    authorization_revision: 1,
    idempotency_key: "distribution-fixture",
  });
  expect(result.dry_run).toBe(true);
  expect(result.distribution_id).toBeNull();
});

it("reads per-target distribution state through the shared contract", async () => {
  request.mockImplementation((path, options) => {
    expect(path).toBe(
      `/v1/corporate/organizations/${organizationId}/catalog-assignments/distribution`,
    );
    expect(options?.method).toBeUndefined();
    expect(options?.query).toMatchObject({
      source_assignment_id: sourceId,
      offset: "5",
      limit: "25",
    });
    return {
      schema_version: 1,
      organization_id: organizationId,
      source_assignment_id: sourceId,
      source_revision: 2,
      source_state: "current",
      items: [
        {
          target_kind: "employee",
          target_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
          result: "applied",
          state: "outdated",
          operation_revision: 1,
        },
      ],
      total: 1,
    };
  });
  const result = await readCorporateAssignmentDistribution("session", organizationId, {
    source_assignment_id: sourceId,
    offset: 5,
    limit: 25,
  });
  expect(result.source_revision).toBe(2);
  expect(result.items[0]?.state).toBe("outdated");
});

it("omits optional pagination when it is not supplied", async () => {
  request.mockImplementation((_path, options) => {
    expect(options?.query?.offset).toBeUndefined();
    expect(options?.query?.limit).toBeUndefined();
    return {
      schema_version: 1,
      organization_id: organizationId,
      source_assignment_id: sourceId,
      source_revision: 1,
      source_state: "current",
      items: [],
      total: 0,
    };
  });
  const result = await readCorporateAssignmentDistribution("session", organizationId, {
    source_assignment_id: sourceId,
  });
  expect(result.total).toBe(0);
});

it("posts the plan request to the shared contract route", async () => {
  request.mockImplementation((path, options) => {
    expect(path).toBe(`/v1/corporate/organizations/${organizationId}/catalog-assignments/plan`);
    expect(options?.method).toBe("POST");
    expect(options?.body).toMatchObject({
      account_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
      harness: "claude-code",
      materialized: [
        { object_kind: "setup", stable_id: "setup_01JQZK7B8N4M6P2R9T5V0X3Y7Z", version: "1.0" },
      ],
    });
    return {
      schema_version: 1,
      organization_id: organizationId,
      account_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
      harness: "claude-code",
      items: [
        {
          object_kind: "setup",
          stable_id: "setup_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
          state: "assigned",
          outcome: "installed",
          action: "none",
          version: "1.0",
          installed_version: "1.0",
        },
      ],
      total: 1,
    };
  });
  const result = await planCorporateAssignment("session", organizationId, {
    schema_version: 1,
    account_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    harness: "claude-code",
    materialized: [
      { object_kind: "setup", stable_id: "setup_01JQZK7B8N4M6P2R9T5V0X3Y7Z", version: "1.0" },
    ],
  });
  expect(result.total).toBe(1);
  expect(result.items[0]?.outcome).toBe("installed");
});
