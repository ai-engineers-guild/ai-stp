import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { JSON_SCHEMA, load } from "js-yaml";
import { z } from "zod";

export const CONTENT_TYPES = ["article", "blog_post", "changelog", "release_notes"] as const;
export type ContentType = (typeof CONTENT_TYPES)[number];

const contentMetaSchema = z
  .object({
    type: z.enum(CONTENT_TYPES),
    slug: z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/),
    locale: z.enum(["en", "ru"]),
    title: z.string().min(1).max(160),
    description: z.string().min(1).max(320),
    published_at: z.iso.date(),
    tags: z.array(z.string().min(1).max(40)).max(12),
    draft: z.boolean().default(false),
  })
  .strict();

export type ContentEntry = z.infer<typeof contentMetaSchema> & {
  body: string;
};

function contentRoot(): string {
  return process.env.AI_STP_USER_FACING_ROOT
    ? path.join(process.env.AI_STP_USER_FACING_ROOT, "content")
    : path.resolve(process.cwd(), "..", "..", "docs-user-facing", "content");
}

function parseFile(file: string): ContentEntry {
  const source = readFileSync(file, "utf8");
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
  if (!match) throw new Error(`Content entry lacks YAML frontmatter: ${path.basename(file)}`);
  const rawMeta = load(match[1] ?? "", { json: false, schema: JSON_SCHEMA });
  const parsed = contentMetaSchema.safeParse(rawMeta);
  if (!parsed.success) {
    const details = parsed.error.issues
      .map((issue) => `${issue.path.join(".")}: ${issue.message}`)
      .join("; ");
    throw new Error(`Invalid content entry ${path.basename(file)}: ${details}`);
  }
  const today = new Date().toISOString().slice(0, 10);
  if (parsed.data.published_at > today) {
    throw new Error(`Content entry has a future publication date: ${path.basename(file)}`);
  }
  const body = (match[2] ?? "").trim();
  if (!body) throw new Error(`Content entry body is empty: ${path.basename(file)}`);
  return { ...parsed.data, body };
}

let cached: ContentEntry[] | null = null;

export function resetContentCache(): void {
  cached = null;
}

export function allContentEntries(): ContentEntry[] {
  if (cached) return cached;
  const entries = readdirSync(contentRoot(), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".md"))
    .map((entry) => parseFile(path.join(entry.parentPath, entry.name)));
  const seen = new Set<string>();
  for (const entry of entries) {
    const identity = `${entry.locale}:${entry.type}:${entry.slug}`;
    if (seen.has(identity)) throw new Error(`Duplicate content entry: ${identity}`);
    seen.add(identity);
  }
  cached = entries.sort((a, b) => b.published_at.localeCompare(a.published_at));
  return cached;
}

export function publishedContent(locale: string): ContentEntry[] {
  return allContentEntries().filter((entry) => entry.locale === locale && !entry.draft);
}

export function findContent(locale: string, type: string, slug: string): ContentEntry | null {
  return (
    publishedContent(locale).find((entry) => entry.type === type && entry.slug === slug) ?? null
  );
}

export function assertContentLocaleParity(): void {
  const entries = allContentEntries().filter((entry) => !entry.draft);
  const en = new Set(entries.filter((entry) => entry.locale === "en").map(identityWithoutLocale));
  const ru = new Set(entries.filter((entry) => entry.locale === "ru").map(identityWithoutLocale));
  const missing = [...en]
    .filter((item) => !ru.has(item))
    .concat([...ru].filter((item) => !en.has(item)));
  if (missing.length > 0)
    throw new Error(`Content locale parity failed: ${missing.sort().join(", ")}`);
}

function identityWithoutLocale(entry: ContentEntry): string {
  return `${entry.type}:${entry.slug}`;
}
