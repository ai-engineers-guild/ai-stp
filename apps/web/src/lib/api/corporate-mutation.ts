import type { FieldErrors } from "@/lib/api/field-errors";

export type CorporateMutationInput = {
  csrfToken: string;
  organizationId: string;
  path: string;
  method: "POST" | "PUT" | "PATCH" | "DELETE";
  body: unknown;
};

export type CorporateMutationResult =
  | { ok: true; data: unknown }
  | { ok: false; message: string; code?: string; fieldErrors?: FieldErrors };

/**
 * Client-side write path for the corporate workspace: a plain fetch to the
 * `/api/corporate/mutation` route handler, so a stale build can never strand
 * this page on a dead server-action ID. The handler repeats CSRF, session,
 * and path checks before forwarding to the API, which remains the authority.
 */
export async function corporateMutation(
  input: CorporateMutationInput,
): Promise<CorporateMutationResult> {
  try {
    const response = await fetch("/api/corporate/mutation", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-csrf-token": input.csrfToken,
        "x-locale": document.documentElement.lang,
      },
      body: JSON.stringify({
        organizationId: input.organizationId,
        path: input.path,
        method: input.method,
        body: input.body,
      }),
    });
    return (await response.json()) as CorporateMutationResult;
  } catch {
    // Mirrors the transport-failure ApiError the old server action surfaced.
    return { ok: false, code: "AI_STP_UNAVAILABLE", message: "API unavailable" };
  }
}

export type CorporateTeamAssignment = {
  accountId: string;
  teamId: string;
  role: "staff" | "lead";
  operation: "assign" | "remove";
  idempotencyKey: string;
};

export async function corporateTeamAssignments(input: {
  csrfToken: string;
  organizationId: string;
  assignments: CorporateTeamAssignment[];
}): Promise<{ completed: string[]; message?: string }> {
  try {
    const response = await fetch("/api/corporate/team-assignments", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-csrf-token": input.csrfToken,
        "x-locale": document.documentElement.lang,
      },
      body: JSON.stringify({
        organizationId: input.organizationId,
        assignments: input.assignments,
      }),
    });
    return (await response.json()) as { completed: string[]; message?: string };
  } catch {
    return { completed: [], message: "API unavailable" };
  }
}
