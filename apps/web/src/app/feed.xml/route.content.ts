import { listPublishedContent } from "@/lib/api/content";
import { isFeatureEnabled } from "@/lib/features/gate";
import { publicOrigin } from "@/lib/site";

function xml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export async function GET() {
  if (!isFeatureEnabled("content_hub")) return new Response("Not found", { status: 404 });
  const origin = publicOrigin();
  const items = (await listPublishedContent("en"))
    .map((entry) => {
      const href = new URL(`/en/content/${entry.type}/${entry.slug}`, origin).toString();
      return `<entry><title>${xml(entry.title)}</title><id>${xml(href)}</id><link href="${xml(href)}"/><updated>${entry.published_at}T00:00:00Z</updated><summary>${xml(entry.description)}</summary></entry>`;
    })
    .join("");
  const body = `<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>ai_stp content</title><id>${xml(origin.toString())}</id>${items}</feed>`;
  return new Response(body, {
    headers: {
      "content-type": "application/atom+xml; charset=utf-8",
      "cache-control": "public, max-age=3600",
    },
  });
}
