import { describe, expect, it } from "vitest";

import { tokenizeJson } from "@/lib/json-highlight";

describe("tokenizeJson", () => {
  it("marks keys, strings and literals without inventing fields", () => {
    const tokens = tokenizeJson('{\n  "name": "demo",\n  "ok": true\n}');
    expect(tokens.some((token) => token.type === "key" && token.value === '"name"')).toBe(true);
    expect(tokens.some((token) => token.type === "string" && token.value === '"demo"')).toBe(true);
    expect(tokens.some((token) => token.type === "literal" && token.value === "true")).toBe(true);
    expect(tokens.map((token) => token.value).join("")).toBe(
      '{\n  "name": "demo",\n  "ok": true\n}',
    );
  });
});
