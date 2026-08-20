import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Negative check (REQ-2310): client components must not implement authorization
 * grants or write paths that the CLI cannot reach.
 */
function walk(dir: string): string[] {
  const entries = readdirSync(dir);
  const files: string[] = [];
  for (const entry of entries) {
    const full = path.join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      files.push(...walk(full));
    } else if (full.endsWith(".ts") || full.endsWith(".tsx")) {
      files.push(full);
    }
  }
  return files;
}

describe("no frontend-only authorization", () => {
  it("client components do not decide grants or invent private write routes", () => {
    const root = path.resolve(__dirname, "../../src");
    const files = walk(root);
    const clientFiles = files.filter((file) => {
      const text = readFileSync(file, "utf8");
      return text.includes('"use client"') || text.includes("'use client'");
    });
    for (const file of clientFiles) {
      const text = readFileSync(file, "utf8");
      expect(text).not.toMatch(/canAccess|isAuthorized|authorize\(/);
      expect(text).not.toMatch(/localStorage\.setItem\(['"]access_token/);
      expect(text).not.toMatch(/sessionStorage\.setItem\(['"](access|refresh)_token/);
    }
  });

  it("share controls are confined to public catalog detail routes", () => {
    const root = path.resolve(__dirname, "../../src/app");
    const importers = walk(root).filter((file) =>
      readFileSync(file, "utf8").includes("import { ObjectDetailHeader }"),
    );
    expect(importers).toHaveLength(2);
    for (const file of importers) {
      expect(file.replaceAll("\\", "/")).toMatch(
        /\/catalog\/(components|setups)\/\[stableId\]\/page\.tsx$/,
      );
    }
  });
});
