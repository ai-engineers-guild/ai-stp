import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/errors";
import { apiRequestBinary } from "@/lib/api/http";
import { sessionCookieValue } from "@/lib/auth/require-session";
import {
  COMPONENT_MEDIA_MAX_BYTES,
  isComponentMediaMime,
  kindFromMime,
} from "@/lib/component-media";

/** Same-origin binary bridge avoids Server Action multipart/body-size limits. */
export async function POST(request: Request, context: { params: Promise<{ stableId: string }> }) {
  const { stableId } = await context.params;
  if (!stableId || stableId.length < 8 || stableId.length > 64) {
    return NextResponse.json({ message: "invalid component id" }, { status: 400 });
  }

  const contentType =
    request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase() ?? "";
  if (!isComponentMediaMime(contentType) || !kindFromMime(contentType)) {
    return NextResponse.json({ message: "unsupported component media mime type" }, { status: 400 });
  }

  const contentLengthHeader = request.headers.get("content-length");
  if (contentLengthHeader) {
    const declared = Number(contentLengthHeader);
    if (Number.isFinite(declared) && declared > COMPONENT_MEDIA_MAX_BYTES) {
      return NextResponse.json(
        { message: "component media exceeds 25 MiB limit" },
        { status: 413 },
      );
    }
    if (Number.isFinite(declared) && declared <= 0) {
      return NextResponse.json({ message: "empty component media payload" }, { status: 400 });
    }
  }

  let body: ArrayBuffer;
  try {
    body = await request.arrayBuffer();
  } catch {
    return NextResponse.json({ message: "component media upload failed" }, { status: 400 });
  }

  if (body.byteLength <= 0) {
    return NextResponse.json({ message: "empty component media payload" }, { status: 400 });
  }
  if (body.byteLength > COMPONENT_MEDIA_MAX_BYTES) {
    return NextResponse.json({ message: "component media exceeds 25 MiB limit" }, { status: 413 });
  }

  try {
    const sessionToken = await sessionCookieValue();
    const result = await apiRequestBinary(
      `/v1/owner/objects/component/${encodeURIComponent(stableId)}/presentation/media`,
      {
        method: "POST",
        contentType,
        body,
        ...(sessionToken ? { sessionToken } : {}),
      },
    );
    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json(
        { message: error.message, code: error.code },
        { status: error.status || 502 },
      );
    }
    return NextResponse.json({ message: "component media upload failed" }, { status: 502 });
  }
}
