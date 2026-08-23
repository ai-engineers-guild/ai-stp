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

const FIELD_WORDS = ["NAME", "TAGS", "HARNESS", "TYPE", "AUTHOR", "VERIFIED"] as const;
const OPERATOR_WORDS = ["AND", "OR", "NOT", "IN"] as const;

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
  if (/(?:^|[\s(])(?:NAME|TAGS|HARNESS|TYPE|AUTHOR|VERIFIED)\s*$/i.test(value)) {
    return [...FIELD_OPERATORS];
  }
  const activeToken = value.match(/[A-Za-z_]+$/)?.[0]?.toUpperCase() ?? "";
  if (!activeToken) return [];
  return CATALOG_QL_WORDS.filter(
    (word) => word.startsWith(activeToken) && word !== activeToken,
  ).slice(0, 5);
}

export function correctCatalogQuery(value: string): string {
  if (!looksLikeCatalogQl(value)) return value;
  return value.replace(/\b[A-Za-z_]+\b/g, (word, offset: number) => {
    if (isFieldPosition(value, offset, word.length)) {
      return canonicalField(word) ?? word;
    }
    if (isInsideFieldValue(value, offset)) return word;
    return canonicalOperator(word) ?? word;
  });
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
