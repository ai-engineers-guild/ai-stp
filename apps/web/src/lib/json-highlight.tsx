import type { ReactNode } from "react";

export type JsonTokenType = "key" | "string" | "number" | "literal" | "punctuation" | "whitespace";

export type JsonToken = {
  type: JsonTokenType;
  value: string;
};

const TOKEN =
  /("(?:\\.|[^"\\])*")\s*:|("(?:\\.|[^"\\])*")|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|[{}[\],:]|\s+/g;

export function tokenizeJson(source: string): JsonToken[] {
  const tokens: JsonToken[] = [];
  let cursor = 0;
  for (const match of source.matchAll(TOKEN)) {
    const index = match.index;
    if (index > cursor) {
      tokens.push({ type: "punctuation", value: source.slice(cursor, index) });
    }
    const [lexeme, key, stringLiteral] = match;
    if (key !== undefined) {
      const colon = lexeme.slice(key.length);
      tokens.push({ type: "key", value: key });
      if (colon) tokens.push({ type: "punctuation", value: colon });
    } else if (stringLiteral !== undefined) {
      tokens.push({ type: "string", value: stringLiteral });
    } else if (lexeme === "true" || lexeme === "false" || lexeme === "null") {
      tokens.push({ type: "literal", value: lexeme });
    } else if (/^\s+$/.test(lexeme)) {
      tokens.push({ type: "whitespace", value: lexeme });
    } else if (/^-?\d/.test(lexeme)) {
      tokens.push({ type: "number", value: lexeme });
    } else {
      tokens.push({ type: "punctuation", value: lexeme });
    }
    cursor = index + lexeme.length;
  }
  if (cursor < source.length) {
    tokens.push({ type: "punctuation", value: source.slice(cursor) });
  }
  return tokens;
}

const TOKEN_CLASS: Record<JsonTokenType, string> = {
  key: "text-foreground font-medium",
  string: "text-success",
  number: "text-foreground tabular-nums",
  literal: "text-warning",
  punctuation: "text-muted-foreground",
  whitespace: "",
};

export function highlightedJson(source: string): ReactNode[] {
  return tokenizeJson(source).map((token, index) => (
    <span key={`${token.type}-${index}`} className={TOKEN_CLASS[token.type] || undefined}>
      {token.value}
    </span>
  ));
}
