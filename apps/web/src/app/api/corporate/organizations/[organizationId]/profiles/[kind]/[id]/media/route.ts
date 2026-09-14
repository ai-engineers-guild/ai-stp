import { NextResponse } from "next/server";
import { z } from "zod";

import { assertCsrf, readCsrfToken } from "@/lib/auth/session";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { ApiError } from "@/lib/api/errors";
import { apiRequestBinary } from "@/lib/api/http";
import { readBoundedUpload, UploadBodyError } from "@/lib/bounded-upload";
import {
  COMPONENT_MEDIA_MAX_BYTES,
  isComponentMediaMime,
  kindFromMime,
} from "@/lib/component-media";
import { corporatePresentationPath, type CorporateDetailResource } from "@/lib/corporate-detail";

const resourceByKind: Record<string, CorporateDetailResource> = {
  team: "teams",
  project: "projects",
  employee: "members",
  technology: "technologies",
};
const uploadQuerySchema = z
  .object({
    purpose: z.enum(["avatar", "media"]),
    expected_revision: z.string().regex(/^\d+$/).transform(Number).pipe(z.number().int().safe()),
    authorization_revision: z
      .string()
      .regex(/^[1-9]\d*$/)
      .transform(Number)
      .pipe(z.number().int().safe()),
  })
  .strict();
const idempotencyKeySchema = z.string().regex(/^[A-Za-z0-9._~-]{16,128}$/);

// eslint-disable-next-line complexity -- One BFF owns the complete binary trust boundary.
export async function POST(
  request: Request,
  context: { params: Promise<{ organizationId: string; kind: string; id: string }> },
): Promise<NextResponse> {
  try {
    assertCsrf(request.headers.get("x-csrf-token"), await readCsrfToken());
  } catch {
    return NextResponse.json({ message: "csrf failed" }, { status: 403 });
  }
  const sessionToken = await sessionCookieValue();
  if (!sessionToken) return NextResponse.json({ message: "not signed in" }, { status: 401 });

  const { organizationId, kind, id } = await context.params;
  const resource = resourceByKind[kind];
  if (!resource) return NextResponse.json({ message: "invalid corporate target" }, { status: 400 });
  let upstreamPath: string;
  try {
    upstreamPath = corporatePresentationPath(organizationId, resource, id).replace(
      "/entity-profiles/",
      "/profiles/",
    );
  } catch {
    return NextResponse.json({ message: "invalid corporate target" }, { status: 400 });
  }

  const parsedQuery = uploadQuerySchema.safeParse(
    Object.fromEntries(new URL(request.url).searchParams),
  );
  const idempotencyKey = idempotencyKeySchema.safeParse(
    request.headers.get("idempotency-key") ?? "",
  );
  if (!parsedQuery.success || !idempotencyKey.success) {
    return NextResponse.json({ message: "invalid upload request" }, { status: 400 });
  }

  const contentType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  const { purpose, expected_revision, authorization_revision } = parsedQuery.data;
  const validType =
    purpose === "avatar"
      ? contentType !== undefined && ["image/png", "image/jpeg", "image/webp"].includes(contentType)
      : contentType !== undefined && isComponentMediaMime(contentType) && kindFromMime(contentType);
  if (!validType || !contentType) {
    return NextResponse.json({ message: "unsupported corporate media mime type" }, { status: 400 });
  }

  let body: ArrayBuffer;
  try {
    body = await readBoundedUpload(
      request,
      purpose === "avatar" ? 5 * 1024 * 1024 : COMPONENT_MEDIA_MAX_BYTES,
    );
  } catch (error) {
    if (error instanceof UploadBodyError && error.reason === "oversized") {
      return NextResponse.json({ message: "corporate media exceeds size limit" }, { status: 413 });
    }
    const message =
      error instanceof UploadBodyError && error.reason === "empty"
        ? "empty corporate media payload"
        : "corporate media upload failed";
    return NextResponse.json({ message }, { status: 400 });
  }

  const query = new URLSearchParams({
    purpose,
    expected_revision: String(expected_revision),
    authorization_revision: String(authorization_revision),
  });
  try {
    const result = await apiRequestBinary(`${upstreamPath}/media?${query.toString()}`, {
      method: "POST",
      contentType,
      body,
      sessionToken,
      headers: {
        "X-CSRF-Token": request.headers.get("x-csrf-token") ?? "",
        "Idempotency-Key": idempotencyKey.data,
      },
    });
    return NextResponse.json(result, { status: 200 });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json(
        { message: error.message, code: error.code },
        { status: error.status || 502 },
      );
    }
    return NextResponse.json({ message: "corporate media upload failed" }, { status: 502 });
  }
}
