import { NextResponse } from "next/server";

import { readMockCorporateMedia } from "@/lib/api/mock-corporate";
import { getEnv } from "@/lib/env";

export const dynamic = "force-dynamic";

/** Synthetic corporate fixture delivery; production assets remain API-owned. */
export async function GET(
  _request: Request,
  context: { params: Promise<{ assetId: string }> },
): Promise<NextResponse> {
  if (!getEnv().AI_STP_USE_MOCKS) return new NextResponse(null, { status: 404 });
  const { assetId } = await context.params;
  if (!/^avatar_[a-f0-9]{24}$/.test(assetId)) return new NextResponse(null, { status: 404 });
  const media = readMockCorporateMedia(assetId);
  if (!media) return new NextResponse(null, { status: 404 });
  return new NextResponse(media.body, {
    status: 200,
    headers: {
      "Cache-Control": "public, max-age=60",
      "Content-Type": media.contentType,
    },
  });
}
