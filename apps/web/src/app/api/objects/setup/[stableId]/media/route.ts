import { NextResponse } from "next/server";
import { ApiError } from "@/lib/api/errors";
import { apiRequestBinary } from "@/lib/api/http";
import { sessionCookieValue } from "@/lib/auth/require-session";
import {
  COMPONENT_MEDIA_MAX_BYTES,
  isComponentMediaMime,
  kindFromMime,
} from "@/lib/component-media";
export async function POST(request: Request, context: { params: Promise<{ stableId: string }> }) {
  const { stableId } = await context.params;
  const contentType =
    request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase() ?? "";
  if (
    !stableId ||
    stableId.length < 8 ||
    stableId.length > 64 ||
    !isComponentMediaMime(contentType) ||
    !kindFromMime(contentType)
  ) {
    return NextResponse.json({ message: "invalid setup media upload" }, { status: 400 });
  }
  const body = await request.arrayBuffer();
  if (body.byteLength <= 0 || body.byteLength > COMPONENT_MEDIA_MAX_BYTES) {
    return NextResponse.json({ message: "setup media size out of bounds" }, { status: 413 });
  }
  try {
    const sessionToken = await sessionCookieValue();
    const result = await apiRequestBinary(
      `/v1/owner/objects/setup/${encodeURIComponent(stableId)}/presentation/media`,
      { method: "POST", contentType, body, ...(sessionToken ? { sessionToken } : {}) },
    );
    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    if (error instanceof ApiError)
      return NextResponse.json(
        { message: error.message, code: error.code },
        { status: error.status || 502 },
      );
    return NextResponse.json({ message: "setup media upload failed" }, { status: 502 });
  }
}
