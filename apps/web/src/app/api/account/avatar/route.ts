import { readBoundedUpload, UploadBodyError } from "@/lib/bounded-upload";
import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/errors";
import { apiRequestBinary } from "@/lib/api/http";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { assertCsrf, readCsrfToken } from "@/lib/auth/session";

/** Same-origin binary bridge avoids Server Action multipart/body-size limits. */
export async function POST(request: Request) {
  try {
    assertCsrf(request.headers.get("x-csrf-token"), await readCsrfToken());
  } catch {
    return NextResponse.json({ message: "csrf failed" }, { status: 403 });
  }
  const sessionToken = await sessionCookieValue();
  if (!sessionToken) return NextResponse.json({ message: "not signed in" }, { status: 401 });
  const contentType = request.headers.get("content-type")?.split(";", 1)[0]?.trim() ?? "";
  if (!["image/png", "image/jpeg", "image/webp"].includes(contentType)) {
    return NextResponse.json({ message: "unsupported avatar mime type" }, { status: 400 });
  }
  let body: ArrayBuffer;
  try {
    body = await readBoundedUpload(request, 5 * 1024 * 1024);
  } catch (error) {
    const oversized = error instanceof UploadBodyError && error.reason === "oversized";
    return NextResponse.json(
      { message: oversized ? "avatar exceeds 5 MiB limit" : "invalid avatar body" },
      { status: oversized ? 413 : 400 },
    );
  }
  try {
    const result = await apiRequestBinary("/v1/account/public-profile/avatar", {
      method: "POST",
      contentType,
      body,
      sessionToken,
    });
    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json(
        { message: error.message, code: error.code },
        { status: error.status || 502 },
      );
    }
    return NextResponse.json({ message: "avatar upload failed" }, { status: 502 });
  }
}
