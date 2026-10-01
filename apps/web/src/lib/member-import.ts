/**
 * Bulk member import: extract {displayName, email} pairs from CSV/TSV, JSON,
 * Markdown, XML, HTML, or plain text. The parser is intentionally forgiving —
 * every format degrades to per-line email extraction with the leftover text
 * as the display name.
 */

export type ImportedMember = { displayName: string; email: string };
export type MemberImportRow = ImportedMember & {
  rowNumber: number;
  error: "invalidEmail" | "nameTooLong" | "duplicateEmail" | null;
};
export const MEMBER_IMPORT_LIMIT = 500;

const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;
const EMAIL_GLOBAL = new RegExp(EMAIL.source, "g");
const EXT_JSON = /\.json$/i;
const EXT_MARKUP = /\.(xml|html?|xhtml|svg)$/i;

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
  if (!EXT_MARKUP.test(filename))
    return inspectMemberImport(text, filename)
      .filter((row) => row.error === null)
      .map(({ email, displayName }) => ({ email, displayName }));
  const out: ImportedMember[] = [];
  const seen = new Set<string>();
  let source = text;
  if (EXT_MARKUP.test(filename)) {
    source = source
      .replace(MARKUP_ROW_BOUNDARY, "\n")
      .replace(/<[^>]+>/g, " ")
      .replace(/&[a-z#0-9]+;/gi, " ");
  }
  for (const line of source.split(/\r?\n/)) {
    if (lineIsSkippable(line) || !EMAIL.test(line)) continue;
    fromLine(line, out, seen);
  }
  return out;
}

/** Parse delimited records without treating optional role columns as a name. */
function tableCells(text: string, delimiter: string): string[][] {
  const rows: string[][] = [];
  let cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < text.length; index++) {
    const char = text[index];
    if (char === '"') {
      if (quoted && text[index + 1] === '"') {
        cell += '"';
        index++;
      } else quoted = !quoted;
    } else if (!quoted && (char === delimiter || char === "\n")) {
      cells.push(cell.trim());
      cell = "";
      if (char === "\n") {
        rows.push(cells);
        cells = [];
      }
    } else cell += char ?? "";
  }
  if (quoted) throw new Error("Unclosed quoted field");
  cells.push(cell.trim());
  rows.push(cells);
  return rows.filter((row) => row.some(Boolean));
}

const emailHeaders = ["email", "mail", "emailaddress", "address"];
const nameHeaders = ["displayname", "name", "fullname", "title"];
const cellText = (value: unknown): string =>
  typeof value === "string" || typeof value === "number" || typeof value === "boolean"
    ? String(value)
    : "";
const headerKey = (value: unknown) =>
  cellText(value)
    .toLowerCase()
    .replace(/[^a-z]/g, "");

/** Common CSV, Markdown and spreadsheet column projection. Values remain text. */
export function inspectMemberCells(cells: readonly (readonly unknown[])[]): MemberImportRow[] {
  const first = cells[0] ?? [];
  const headers = first.map(headerKey);
  const emailColumn = headers.findIndex((value) => emailHeaders.includes(value));
  const nameColumn = headers.findIndex((value) => nameHeaders.includes(value));
  const hasHeader = emailColumn >= 0;
  const records = (hasHeader ? cells.slice(1) : cells).filter(
    (row) =>
      row.some((value) => cellText(value).trim()) &&
      !row.every((value) => /^[\s:|-]*$/.test(cellText(value))),
  );
  if (records.length > MEMBER_IMPORT_LIMIT) throw new Error("Too many recipients");
  const seen = new Set<string>();
  return records.map((record, index) => {
    let values = record.map((value) => cellText(value).trim());
    if (hasHeader && values.length === 1 && EMAIL.test(values[0] ?? "")) {
      const line = values[0] ?? "";
      values = headers.map((_, index) =>
        index === emailColumn
          ? (line.match(EMAIL)?.[0] ?? "")
          : index === nameColumn
            ? cleanName(line)
            : "",
      );
    }
    const emailIndex = hasHeader ? emailColumn : values.findIndex((value) => EMAIL.test(value));
    const email = (values[emailIndex] ?? values[0] ?? "").trim().toLowerCase();
    const displayName =
      (hasHeader
        ? values[nameColumn]
        : values.find(
            (value, cellIndex) =>
              cellIndex !== emailIndex && value && !["staff", "lead", "superadmin"].includes(value),
          )) || email;
    const error =
      email.length > 320 || !new RegExp(`^${EMAIL.source}$`).test(email)
        ? "invalidEmail"
        : displayName.length > 80
          ? "nameTooLong"
          : seen.has(email)
            ? "duplicateEmail"
            : null;
    if (error === null) seen.add(email);
    return { email, displayName, rowNumber: index + (hasHeader ? 2 : 1), error };
  });
}

export function inspectMemberImport(text: string, filename = ""): MemberImportRow[] {
  const source = text.replace(/^\uFEFF/, "").trim();
  if (!source) return [];
  if (EXT_JSON.test(filename) || /^[{[]/.test(source)) {
    const data: unknown = JSON.parse(source);
    const rows = Array.isArray(data) ? data : [data];
    const cells = rows.map((row) => {
      if (typeof row === "string") return [row, row];
      if (!row || typeof row !== "object") return [String(row), ""];
      const record = row as Record<string, unknown>;
      const key = (aliases: string[]) =>
        Object.entries(record).find(([name]) => aliases.includes(headerKey(name)))?.[1];
      return [key(emailHeaders) ?? JSON.stringify(row), key(nameHeaders) ?? ""];
    });
    return inspectMemberCells([["email", "display_name"], ...cells]);
  }
  const first = source.split(/\r?\n/)[0] ?? "";
  const delimiter = ["\t", ",", ";", "|"].find((value) => first.includes(value));
  if (delimiter) {
    // Legacy pasted lists sometimes mix CSV and TSV rows.
    const normalized = delimiter === "," ? source.replace(/\t/g, ",") : source;
    return inspectMemberCells(tableCells(normalized, delimiter));
  }
  const cells = source
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => {
      const email = line.match(EMAIL)?.[0] ?? "";
      return [email, cleanName(line) || email];
    });
  return inspectMemberCells([["email", "display_name"], ...cells]);
}
