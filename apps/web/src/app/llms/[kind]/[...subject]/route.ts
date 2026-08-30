import { notFound } from "next/navigation";

import { readSeoProfile, type SeoSubjectKind } from "@/lib/api/seo";
import { renderSeoMarkdown } from "@/lib/seo/markdown";

const KINDS = new Set<SeoSubjectKind>(["component", "setup", "article", "service", "country"]);

export async function GET(
  request: Request,
  context: { params: Promise<{ kind: string; subject: string[] }> },
) {
  const { kind, subject } = await context.params;
  if (!KINDS.has(kind as SeoSubjectKind)) notFound();
  const last = subject.at(-1) ?? "";
  const trimmed = last.endsWith(".md") ? [...subject.slice(0, -1), last.slice(0, -4)] : subject;
  const subjectId = trimmed.join("/");
  const locale = new URL(request.url).searchParams.get("locale") === "ru" ? "ru" : "en";
  const profile = await readSeoProfile(kind as SeoSubjectKind, subjectId, locale);
  if (!profile) notFound();
  return new Response(renderSeoMarkdown(profile), {
    headers: {
      "content-type": "text/markdown; charset=utf-8",
      "cache-control": "public, max-age=60",
    },
  });
}
