import { revalidatePath } from "next/cache";
import { NextResponse } from "next/server";
import { getTranslations } from "next-intl/server";

import { ApiError } from "@/lib/api/errors";
import { fieldErrorsFromDetails } from "@/lib/api/field-errors";
import { privateApiRequest, type PrivateRequestOptions } from "@/lib/api/http";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { assertCsrf, readCsrfToken, readSession } from "@/lib/auth/session";
import { defaultLocale, isAppLocale, type AppLocale } from "@/lib/i18n/routing";

export const dynamic = "force-dynamic";

const METHODS = new Set<"POST" | "PUT" | "PATCH" | "DELETE">(["POST", "PUT", "PATCH", "DELETE"]);

type MutationMethod = "POST" | "PUT" | "PATCH" | "DELETE";

function requestedLocale(request: Request): AppLocale {
  const header = request.headers.get("x-locale");
  return header && isAppLocale(header) ? header : defaultLocale;
}

/**
 * Corporate write proxy, kept out of the server-action manifest so that a
 * long-lived page never calls an action ID a fresh build has replaced.
 * Repeats the action's checks verbatim: double-submit CSRF, live session,
 * organization-bound path prefix, then the API enforces its own
 * authorization, revisions, and idempotency.
 */
export async function POST(request: Request) {
  const common = await getTranslations({
    locale: requestedLocale(request),
    namespace: "common",
  });
  const fail = (message: string, status: number, code?: string) =>
    NextResponse.json({ ok: false, message, code }, { status });

  let input: {
    organizationId?: unknown;
    path?: unknown;
    method?: unknown;
    body?: unknown;
  };
  try {
    input = (await request.json()) as typeof input;
  } catch {
    return fail(common("invalidRequest"), 400);
  }
  const organizationId = typeof input.organizationId === "string" ? input.organizationId : "";
  const path = typeof input.path === "string" ? input.path : "";
  const method: MutationMethod | null =
    typeof input.method === "string" && METHODS.has(input.method as MutationMethod)
      ? (input.method as MutationMethod)
      : null;
  if (
    !method ||
    !/^organization_[A-Za-z0-9_-]{20,80}$/.test(organizationId) ||
    !path.startsWith(`/v1/corporate/organizations/${organizationId}/`) ||
    path.includes("..")
  ) {
    return fail(common("invalidRequest"), 400);
  }
  try {
    assertCsrf(request.headers.get("x-csrf-token"), await readCsrfToken());
  } catch {
    return fail(common("invalidRequest"), 403, "AI_STP_CSRF_FAILED");
  }
  if (!(await readSession())) return fail(common("notSignedIn"), 401);
  const sessionToken = await sessionCookieValue();
  if (!sessionToken) return fail(common("notSignedIn"), 401);

  const options: PrivateRequestOptions = {
    method,
    body: input.body,
    sessionToken,
  };
  try {
    const data = await privateApiRequest<unknown>(path, options);
    revalidatePath("/[locale]/corporate", "layout");
    return NextResponse.json({ ok: true, data });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json(
        {
          ok: false,
          message: error.message,
          code: error.code,
          fieldErrors: fieldErrorsFromDetails(error.details, error.message),
        },
        { status: error.status > 0 ? error.status : 503 },
      );
    }
    return fail(common("requestFailed"), 500);
  }
}
