import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/corporate/team-assignments/route";
import { privateApiRequest } from "@/lib/api/http";
import { corporateSubjectSearchAction } from "@/actions/corporate";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next-intl/server", () => ({
  getTranslations: vi.fn(() => Promise.resolve((key: string) => key)),
}));
vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({ get: () => ({ value: "session-fixture" }) }),
}));
vi.mock("@/lib/auth/session", () => ({
  assertCsrf: vi.fn(),
  readCsrfToken: () => Promise.resolve("csrf"),
  readSession: () => Promise.resolve({}),
  SESSION_COOKIE: "session",
  SESSION_TTL_MS: 3_600_000,
}));
vi.mock("@/lib/api/http", () => ({ privateApiRequest: vi.fn() }));

const input = {
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

function call(body: unknown) {
  return POST(
    new Request("http://localhost/api/corporate/team-assignments", {
      method: "POST",
      headers: { "x-csrf-token": "csrf" },
      body: JSON.stringify(body),
    }),
  );
}

describe("corporate assignment batches", () => {
  beforeEach(() => vi.clearAllMocks());
  it("keeps assignable directory rows without inventing a generic state field", async () => {
    vi.mocked(privateApiRequest).mockResolvedValueOnce({
      items: [
        {
          id: "technology_draft",
          name: "Draft technology",
          available_actions: ["technology.update"],
        },
        { id: "technology_readonly", name: "Read only", available_actions: [] },
      ],
    });
    const result = await corporateSubjectSearchAction({
      csrfToken: "csrf",
      organizationId: input.organizationId,
      kind: "technology",
    });
    expect(result).toEqual({
      ok: true,
      items: [{ value: "technology_draft", label: "Draft technology" }],
    });
    expect(privateApiRequest).toHaveBeenCalledWith(
      `/v1/corporate/organizations/${input.organizationId}/directory`,
      expect.objectContaining({
        query: { resource: "technologies", limit: 128 },
        sessionToken: "session-fixture",
      }),
    );
  });
  it("refreshes revision between assignments and reports only completed rows on failure", async () => {
    vi.mocked(privateApiRequest)
      .mockResolvedValueOnce({ organization: { authorization_revision: 3 } })
      .mockResolvedValueOnce({})
      .mockResolvedValueOnce({ organization: { authorization_revision: 4 } })
      .mockRejectedValueOnce(new Error("connection lost"));
    const result = (await (await call(input)).json()) as {
      completed: string[];
      message?: string;
    };
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
    const invalid = (await (await call({ ...input, organizationId: "../foreign" })).json()) as {
      completed: string[];
      message?: string;
    };
    expect(invalid.completed).toEqual([]);
    const oversized = (await (
      await call({
        ...input,
        assignments: Array.from({ length: 257 }, () => input.assignments[0]).filter(
          (row) => row !== undefined,
        ),
      })
    ).json()) as { completed: string[]; message?: string };
    expect(oversized.message).toBeDefined();
    expect(privateApiRequest).not.toHaveBeenCalled();
  });
});
