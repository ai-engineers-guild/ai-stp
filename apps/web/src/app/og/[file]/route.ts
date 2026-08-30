import { notFound } from "next/navigation";

import { publicApiGetBytes } from "@/lib/api/public-http";

export async function GET(_request: Request, context: { params: Promise<{ file: string }> }) {
  const { file } = await context.params;
  if (!file.endsWith(".png")) notFound();
  const revisionId = file.slice(0, -4);
  try {
    const bytes = await publicApiGetBytes(`/v1/seo/og/${revisionId}`);
    return new Response(bytes, {
      headers: {
        "content-type": "image/png",
        "cache-control": "public, max-age=31536000, immutable",
      },
    });
  } catch {
    notFound();
  }
}
