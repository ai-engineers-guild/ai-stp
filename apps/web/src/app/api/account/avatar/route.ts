import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/errors";
import { apiRequestBinary } from "@/lib/api/http";
import { sessionCookieValue } from "@/lib/auth/require-session";

/** Same-origin binary bridge avoids Server Action multipart/body-size limits. */
export async function POST(request: Request) {
  const contentType = request.headers.get("content-type")?.split(";", 1)[0]?.trim() ?? "";
  if (!contentType.startsWith("image/")) {
    return NextResponse.json({ message: "unsupported avatar mime type" }, { status: 400 });
  }
  const body = await request.arrayBuffer();
  try {
    const sessionToken = await sessionCookieValue();
    const result = await apiRequestBinary("/v1/account/public-profile/avatar", {
      method: "POST",
      contentType,
      body,
      ...(sessionToken ? { sessionToken } : {}),
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
