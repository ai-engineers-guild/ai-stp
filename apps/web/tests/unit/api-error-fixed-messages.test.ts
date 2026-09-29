import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Server-action ApiError convention: client-visible `code`/`message`/`status`
 * are compile-time literals, never interpolated strings or variables that
 * could echo request or server data back into the UI.
 */
const webRoot = path.resolve(__dirname, "../..");

function actionSources(): { file: string; source: string }[] {
  const dir = path.join(webRoot, "src/actions");
  return readdirSync(dir)
    .filter((name) => name.endsWith(".ts"))
    .map((name) => ({
      file: `src/actions/${name}`,
      source: readFileSync(path.join(dir, name), "utf8"),
    }));
}

/** Extract the argument object literal of every `new ApiError({ ... })`. */
function apiErrorObjects(source: string): string[] {
  const objects: string[] = [];
  let index = 0;
  for (;;) {
    const start = source.indexOf("new ApiError(", index);
    if (start === -1) return objects;
    let cursor = start + "new ApiError(".length;
    while (source[cursor] === " " || source[cursor] === "\n") cursor += 1;
    if (source[cursor] !== "{") {
      index = cursor;
      continue;
    }
    let depth = 0;
    let quote: string | null = null;
    const open = cursor;
    for (; cursor < source.length; cursor += 1) {
      const char = source[cursor];
      if (quote !== null) {
        if (char === "\\") cursor += 1;
        else if (char === quote) quote = null;
        continue;
      }
      if (char === '"' || char === "'" || char === "`") {
        quote = char;
      } else if (char === "{") {
        depth += 1;
      } else if (char === "}") {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    objects.push(source.slice(open, cursor + 1));
    index = cursor;
  }
}

describe("server-action ApiError fixed messages", () => {
  it("every thrown ApiError uses literal code, message, and status", () => {
    // `message` is either a string literal or a single-argument translator
    // call over a literal key — never a template, variable, or expression
    // that could carry request or server data into the UI.
    const fixedMessage = /message\s*:\s*(?:[A-Za-z_$][\w$]*\(\s*"[^"]*"\s*\)|"[^"]*")\s*[,}]/;
    const offenders: string[] = [];
    let sites = 0;
    for (const { file, source } of actionSources()) {
      for (const object of apiErrorObjects(source)) {
        sites += 1;
        if (!/code\s*:\s*"AI_STP_[A-Z_]+"/.test(object)) {
          offenders.push(`${file}: non-literal code in ${object}`);
        }
        if (!fixedMessage.test(object)) {
          offenders.push(`${file}: non-literal message in ${object}`);
        }
        if (!/status\s*:\s*\d+/.test(object)) {
          offenders.push(`${file}: non-literal status in ${object}`);
        }
      }
    }
    expect(sites).toBeGreaterThan(0);
    expect(offenders).toEqual([]);
  });
});
