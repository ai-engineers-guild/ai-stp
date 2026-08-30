import { readSeoCatalog } from "@/lib/api/seo";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const localeParam = url.searchParams.get("locale");
  const locale = localeParam === "ru" || localeParam === "en" ? localeParam : undefined;
  const kindRaw = url.searchParams.get("kind");
  const kind =
    kindRaw === "component" ||
    kindRaw === "setup" ||
    kindRaw === "article" ||
    kindRaw === "service" ||
    kindRaw === "country"
      ? kindRaw
      : undefined;
  const cursor = url.searchParams.get("cursor") ?? undefined;
  const page = await readSeoCatalog({
    ...(locale ? { locale } : {}),
    ...(kind ? { kind } : {}),
    ...(cursor ? { cursor } : {}),
    page_size: 100,
  });
  const lines = (page?.items ?? []).map((item) => JSON.stringify(item));
  return new Response(lines.join("\n") + (lines.length ? "\n" : ""), {
    headers: {
      "content-type": "application/x-ndjson; charset=utf-8",
      "cache-control": "public, max-age=60",
    },
  });
}
