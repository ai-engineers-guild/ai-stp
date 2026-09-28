/**
 * Bulk member import: extract {displayName, email} pairs from CSV/TSV, JSON,
 * Markdown, XML, HTML, or plain text. The parser is intentionally forgiving —
 * every format degrades to per-line email extraction with the leftover text
 * as the display name.
 */

export type ImportedMember = { displayName: string; email: string };

const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;
const EMAIL_GLOBAL = new RegExp(EMAIL.source, "g");
const EXT_JSON = /\.json$/i;
const EXT_MARKUP = /\.(xml|html?|xhtml|svg)$/i;
const EXT_MARKDOWN = /\.(md|markdown)$/i;

function isEmail(value: string): boolean {
  return EMAIL.test(value.trim());
}

function cleanName(value: string): string {
  return value
    .replace(EMAIL_GLOBAL, "")
    .replace(/[<>()[\]{}"'`]/g, " ")
    .replace(/^\s*[-*+>|;,:.\s]+|\s*[-*+>|;,:.\s]+$/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function push(out: ImportedMember[], seen: Set<string>, displayName: string, email: string): void {
  const normalized = email.trim().toLowerCase();
  if (!isEmail(normalized) || normalized.length > 320 || seen.has(normalized)) return;
  seen.add(normalized);
  out.push({ displayName: displayName.trim().slice(0, 80) || normalized, email: normalized });
}

function fromJson(text: string, out: ImportedMember[], seen: Set<string>): boolean {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return false;
  }
  const rows = Array.isArray(data) ? data : [data];
  for (const row of rows) {
    if (typeof row === "string") {
      if (isEmail(row)) push(out, seen, "", row);
      continue;
    }
    if (row === null || typeof row !== "object") continue;
    const record = row as Record<string, unknown>;
    const email = ["email", "mail", "e-mail", "address"]
      .map((key) => record[key])
      .find((value) => typeof value === "string" && isEmail(value));
    if (typeof email !== "string") continue;
    const name = ["display_name", "displayName", "name", "full_name", "fullName", "title"]
      .map((key) => record[key])
      .find((value) => typeof value === "string" && value.trim());
    push(out, seen, typeof name === "string" ? name : "", email);
  }
  return out.length > 0;
}

const MARKUP_ROW_BOUNDARY =
  /<\/(tr|li|p|user|item|row|entry|div|option|member|record|employee|contact)[^>]*>|<br[^>]*>/gi;

function fromLine(line: string, out: ImportedMember[], seen: Set<string>): void {
  const matches = [...line.matchAll(EMAIL_GLOBAL)];
  for (const [index, match] of matches.entries()) {
    const start = match.index;
    const previous = index > 0 ? matches[index - 1] : undefined;
    const previousEnd = previous ? previous.index + previous[0].length : 0;
    const next = index + 1 < matches.length ? matches[index + 1] : undefined;
    const nextStart = next ? next.index : line.length;
    const name =
      cleanName(line.slice(previousEnd, start)) ||
      cleanName(line.slice(start + match[0].length, nextStart));
    push(out, seen, name, match[0]);
  }
}

function lineIsSkippable(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed) return true;
  // Markdown table separator and CSV header rows.
  if (/^\|?[\s:|-]+\|?$/.test(trimmed) && trimmed.includes("-")) return true;
  const cells = trimmed.split(/[,;\t|]/).map((cell) => cell.trim().toLowerCase());
  return cells.every((cell) =>
    ["email", "e-mail", "mail", "name", "display_name", "displayname", ""].includes(cell),
  );
}

export function parseMemberImport(text: string, filename = ""): ImportedMember[] {
  const out: ImportedMember[] = [];
  const seen = new Set<string>();
  let source = text;
  if (EXT_JSON.test(filename) && fromJson(source, out, seen)) return out;
  if (EXT_MARKUP.test(filename)) {
    source = source
      .replace(MARKUP_ROW_BOUNDARY, "\n")
      .replace(/<[^>]+>/g, " ")
      .replace(/&[a-z#0-9]+;/gi, " ");
  }
  if (EXT_MARKDOWN.test(filename)) {
    source = source.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");
  }
  for (const line of source.split(/\r?\n/)) {
    if (lineIsSkippable(line) || !EMAIL.test(line)) continue;
    fromLine(line, out, seen);
  }
  return out;
}
