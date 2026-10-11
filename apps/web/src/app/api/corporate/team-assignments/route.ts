import { revalidatePath } from "next/cache";
import { NextResponse } from "next/server";
import { getTranslations } from "next-intl/server";

import { ApiError } from "@/lib/api/errors";
import { privateApiRequest } from "@/lib/api/http";
import type { CorporateContext } from "@/lib/api/generated/types.gen";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { assertCsrf, readCsrfToken, readSession } from "@/lib/auth/session";
import { defaultLocale, isAppLocale, type AppLocale } from "@/lib/i18n/routing";

export const dynamic = "force-dynamic";

const MAX_ASSIGNMENTS = 256;

function requestedLocale(request: Request): AppLocale {
  const header = request.headers.get("x-locale");
  return header && isAppLocale(header) ? header : defaultLocale;
}

/**
 * Batched team membership writes, ported from the former server action so a
 * long-lived page never calls an action ID a fresh build has replaced. Each
 * leg refetches the context so the authorization revision is current even
 * when a previous assignment has already bumped it.
 */
export async function POST(request: Request) {
  const common = await getTranslations({
    locale: requestedLocale(request),
    namespace: "common",
  });
  const fail = (message: string, status: number) =>
    NextResponse.json({ completed: [], message }, { status });

  let input: { organizationId?: unknown; assignments?: unknown };
  try {
    input = (await request.json()) as typeof input;
  } catch {
    return fail(common("invalidRequest"), 400);
  }
  const organizationId = typeof input.organizationId === "string" ? input.organizationId : "";
  const assignments = Array.isArray(input.assignments) ? input.assignments : [];
  const validAssignment = (
    item: unknown,
  ): item is {
    accountId: string;
    teamId: string;
    role: "staff" | "lead";
    operation: "assign" | "remove";
    idempotencyKey: string;
  } => {
    if (typeof item !== "object" || item === null) return false;
    const candidate = item as Record<string, unknown>;
    return (
      typeof candidate.accountId === "string" &&
      typeof candidate.teamId === "string" &&
      (candidate.role === "staff" || candidate.role === "lead") &&
      (candidate.operation === "assign" || candidate.operation === "remove") &&
      typeof candidate.idempotencyKey === "string" &&
      candidate.idempotencyKey.length <= 128
    );
  };
  if (
    !/^organization_[A-Za-z0-9_-]{20,80}$/.test(organizationId) ||
    !assignments.length ||
    assignments.length > MAX_ASSIGNMENTS ||
    !assignments.every(validAssignment)
  ) {
    return fail(common("invalidRequest"), 400);
  }
  try {
    assertCsrf(request.headers.get("x-csrf-token"), await readCsrfToken());
  } catch {
    return fail(common("invalidRequest"), 403);
  }
  if (!(await readSession())) return fail(common("notSignedIn"), 401);
  const sessionToken = await sessionCookieValue();
  if (!sessionToken) return fail(common("notSignedIn"), 401);

  const completed: string[] = [];
  const base = `/v1/corporate/organizations/${organizationId}`;
  try {
    for (const assignment of assignments) {
      const context = await privateApiRequest<CorporateContext>(`${base}/context`, {
        sessionToken,
      });
      await privateApiRequest(`${base}/membership-assignments`, {
        sessionToken,
        method: "POST",
        body: {
          schema_version: 1,
          account_id: assignment.accountId,
          team_id: assignment.teamId,
          team_role: assignment.role,
          operation: assignment.operation,
          authorization_revision: context.organization.authorization_revision,
          idempotency_key: assignment.idempotencyKey,
        },
      });
      completed.push(assignment.idempotencyKey);
    }
    return NextResponse.json({ completed });
  } catch (error) {
    return NextResponse.json(
      {
        completed,
        message: error instanceof ApiError ? error.message : common("requestFailed"),
      },
      { status: error instanceof ApiError && error.status > 0 ? error.status : 500 },
    );
  } finally {
    revalidatePath("/[locale]/corporate", "layout");
  }
}
