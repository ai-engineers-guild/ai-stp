import { NextResponse } from "next/server";
import { getTranslations } from "next-intl/server";

import { ApiError } from "@/lib/api/errors";
import { apiRequestBinary } from "@/lib/api/http";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { assertCsrf, readCsrfToken, readSession } from "@/lib/auth/session";
import { defaultLocale, isAppLocale } from "@/lib/i18n/routing";

export const dynamic = "force-dynamic";

const MAX_ICON_BYTES = 5 * 1024 * 1024;
const ICON_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

/**
 * Category-icon upload proxy. The API has no organization-scoped media
 * endpoint; the avatar pipeline already validates and normalizes images to
 * PNG and serves them at /v1/media/avatars/{id}, so an icon is just another
 * stored asset. Category writes still enforce category.update — this route
 * only guards session and double-submit CSRF like the JSON mutation proxy.
 */
export async function POST(request: Request) {
  const common = await getTranslations({
    locale: (() => {
      const header = request.headers.get("x-locale");
      return header && isAppLocale(header) ? header : defaultLocale;
    })(),
    namespace: "common",
  });
  const fail = (message: string, status: number, code?: string) =>
    NextResponse.json({ ok: false, message, code }, { status });

  try {
    assertCsrf(request.headers.get("x-csrf-token"), await readCsrfToken());
  } catch {
    return fail(common("invalidRequest"), 403, "AI_STP_CSRF_FAILED");
  }
  if (!(await readSession())) return fail(common("notSignedIn"), 401);
  const sessionToken = await sessionCookieValue();
  if (!sessionToken) return fail(common("notSignedIn"), 401);

  const contentType = request.headers.get("content-type")?.split(";", 1)[0]?.trim() ?? "";
  if (!ICON_TYPES.has(contentType)) return fail(common("invalidRequest"), 400);
  const body = await request.arrayBuffer();
  if (!body.byteLength || body.byteLength > MAX_ICON_BYTES)
    return fail(common("invalidRequest"), 400);

  try {
    const result = await apiRequestBinary<{
      avatar_asset_id: string;
      public_url: string | null;
    }>("/v1/account/public-profile/avatar", {
      method: "POST",
      sessionToken,
      contentType,
      body,
    });
    if (!result.public_url) return fail(common("requestFailed"), 502);
    return NextResponse.json({ ok: true, icon: result.public_url });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json(
        { ok: false, message: error.message, code: error.code },
        { status: error.status > 0 ? error.status : 503 },
      );
    }
    return fail(common("requestFailed"), 500);
  }
}
