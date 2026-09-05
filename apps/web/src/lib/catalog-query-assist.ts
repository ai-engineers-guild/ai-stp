/** Reserved catalog query-language tokens offered as autocomplete. */
export const CATALOG_QL_WORDS = [
  "NAME",
  "TAGS",
  "HARNESS",
  "TYPE",
  "AUTHOR",
  "VERIFIED",
  "AND",
  "OR",
  "NOT",
  "IN",
] as const;

export const CATALOG_QL_FIELDS = ["NAME", "TAGS", "HARNESS", "TYPE", "AUTHOR", "VERIFIED"] as const;
export const CATALOG_QL_OPERATORS = ["AND", "OR", "NOT", "IN"] as const;
const FIELD_WORDS = CATALOG_QL_FIELDS;
const OPERATOR_WORDS = CATALOG_QL_OPERATORS;

export type CatalogQlTokenKind = "field" | "operator" | "syntax" | "text" | "quoted";
export type CatalogQlSegment = { text: string; kind: CatalogQlTokenKind };

export function catalogQlWordKind(word: string): "field" | "operator" | "syntax" {
  if ((FIELD_WORDS as readonly string[]).includes(word)) return "field";
  if ((OPERATOR_WORDS as readonly string[]).includes(word)) return "operator";
  return "syntax";
}

/** Lightweight display lexer; backend parsing remains authoritative. */
export function highlightCatalogQuery(source: string): CatalogQlSegment[] {
  const segments: CatalogQlSegment[] = [];
  const pattern = /("(?:\\.|[^\\"])*"|'(?:\\.|[^\\'])*'|\b[A-Za-z_]+\b|[:,()])/g;
  let offset = 0;
  for (const match of source.matchAll(pattern)) {
    const index = match.index;
    if (index > offset) segments.push({ text: source.slice(offset, index), kind: "text" });
    const text = match[0];
    const upper = text.toUpperCase();
    const kind =
      text.startsWith('"') || text.startsWith("'")
        ? "quoted"
        : catalogQlWordKind(upper) === "field"
          ? "field"
          : catalogQlWordKind(upper) === "operator"
            ? "operator"
            : /^[,:()]$/.test(text)
              ? "syntax"
              : "text";
    segments.push({ text, kind });
    offset = index + text.length;
  }
  if (offset < source.length) segments.push({ text: source.slice(offset), kind: "text" });
  return segments;
}

const FIELD_FIXES: Record<string, string> = {
  nam: "NAME",
  tag: "TAGS",
  tags: "TAGS",
  harnes: "HARNESS",
  autor: "AUTHOR",
  author: "AUTHOR",
  verifed: "VERIFIED",
  verified: "VERIFIED",
  tipe: "TYPE",
  typ: "TYPE",
};

const FIELD_OPERATORS = [":", "IN", "AND"] as const;

export function suggestCatalogQlWords(value: string): string[] {
  const fieldMatch = value.match(/(?:^|[\s(])(?:NAME|TAGS|HARNESS|TYPE|AUTHOR|VERIFIED)\s*$/i);
  if (fieldMatch && !isInsideQuotes(value, fieldMatch.index ?? 0)) {
    return [...FIELD_OPERATORS];
  }
  const match = value.match(/[A-Za-z_]+$/);
  const activeToken = match?.[0]?.toUpperCase() ?? "";
  if (match && isInsideQuotes(value, value.length - match[0].length)) return [];
  if (!activeToken) return [];
  return CATALOG_QL_WORDS.filter(
    (word) => word.startsWith(activeToken) && word !== activeToken,
  ).slice(0, 5);
}

export function correctCatalogQuery(value: string): string {
  if (!looksLikeCatalogQl(value)) return value;
  return value.replace(/\b[A-Za-z_]+\b/g, (word, offset: number) => {
    if (isInsideQuotes(value, offset)) return word;
    if (isFieldPosition(value, offset, word.length)) {
      return canonicalField(word) ?? word;
    }
    if (isInsideFieldValue(value, offset)) return word;
    return canonicalOperator(word) ?? word;
  });
}

function isInsideQuotes(source: string, offset: number): boolean {
  let quote: string | null = null;
  for (let index = 0; index < offset; index += 1) {
    const char = source[index];
    if (char === "\\" && quote) {
      index += 1;
    } else if (quote === char) {
      quote = null;
    } else if (!quote && (char === '"' || char === "'")) {
      quote = char;
    }
  }
  return quote !== null;
}

export function completeCatalogQlToken(value: string, word: string): string {
  if (word === ":") return value.replace(/\s*$/, "") + ":";
  if (word === "IN" || word === "AND" || word === "OR" || word === "NOT") {
    return value.replace(/\s*$/, "") + ` ${word} `;
  }
  return value.replace(/[A-Za-z_]+$/, word);
}

function looksLikeCatalogQl(value: string): boolean {
  return /(?:^|[\s(])[A-Za-z_]+\s*(?::|(?:NOT\s+)?IN\s*\()/i.test(value);
}

function isFieldPosition(source: string, offset: number, length: number): boolean {
  return /^\s*(?::|(?:NOT\s+)?IN\s*\()/i.test(source.slice(offset + length));
}

function isInsideFieldValue(source: string, offset: number): boolean {
  const lastColon = source.lastIndexOf(":", offset);
  if (lastColon === -1) return false;
  return !/\s/.test(source.slice(lastColon + 1, offset));
}

function canonicalField(word: string): string | undefined {
  const upper = word.toUpperCase();
  if ((FIELD_WORDS as readonly string[]).includes(upper)) return upper;
  return FIELD_FIXES[word.toLowerCase()];
}

function canonicalOperator(word: string): string | undefined {
  const upper = word.toUpperCase();
  if ((OPERATOR_WORDS as readonly string[]).includes(upper)) return upper;
  return undefined;
}
