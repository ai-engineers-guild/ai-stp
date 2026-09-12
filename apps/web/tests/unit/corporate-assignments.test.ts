import { beforeEach, describe, expect, it, vi } from "vitest";

import { corporateTeamAssignmentsAction } from "@/actions/corporate";
import { privateApiRequest } from "@/lib/api/http";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({ get: () => ({ value: "session-fixture" }) }),
}));
vi.mock("@/lib/auth/session", () => ({
  assertCsrf: vi.fn(),
  readCsrfToken: () => Promise.resolve("csrf"),
  readSession: () => Promise.resolve({}),
  SESSION_COOKIE: "session",
}));
vi.mock("@/lib/api/http", () => ({ privateApiRequest: vi.fn() }));

const input = {
  csrfToken: "csrf",
  organizationId: "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  assignments: [
    {
      accountId: "account_A",
      teamId: "operation_A",
      role: "staff" as const,
      operation: "assign" as const,
      idempotencyKey: "assignment-first",
    },
    {
      accountId: "account_B",
      teamId: "operation_A",
      role: "lead" as const,
      operation: "assign" as const,
      idempotencyKey: "assignment-second",
    },
  ],
};

describe("corporate assignment batches", () => {
  beforeEach(() => vi.clearAllMocks());
  it("refreshes revision between assignments and reports only completed rows on failure", async () => {
    vi.mocked(privateApiRequest)
      .mockResolvedValueOnce({ organization: { authorization_revision: 3 } })
      .mockResolvedValueOnce({})
      .mockResolvedValueOnce({ organization: { authorization_revision: 4 } })
      .mockRejectedValueOnce(new Error("connection lost"));
    const result = await corporateTeamAssignmentsAction(input);
    expect(result.completed).toEqual(["assignment-first"]);
    expect(result.message).toBeDefined();
    expect(vi.mocked(privateApiRequest).mock.calls[1]?.[1]?.body).toMatchObject({
      authorization_revision: 3,
      idempotency_key: "assignment-first",
    });
    expect(vi.mocked(privateApiRequest).mock.calls[3]?.[1]?.body).toMatchObject({
      authorization_revision: 4,
      idempotency_key: "assignment-second",
    });
  });
  it("rejects foreign target syntax and oversized batches before API calls", async () => {
    const invalid = await corporateTeamAssignmentsAction({
      ...input,
      organizationId: "../foreign",
    });
    expect(invalid.completed).toEqual([]);
    const oversized = await corporateTeamAssignmentsAction({
      ...input,
      assignments: Array.from({ length: 257 }, () => input.assignments[0]).filter(
        (row) => row !== undefined,
      ),
    });
    expect(oversized.message).toBeDefined();
    expect(privateApiRequest).not.toHaveBeenCalled();
  });
});
