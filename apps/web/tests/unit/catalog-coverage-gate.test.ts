import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const repoRoot = path.resolve(__dirname, "../../../..");

describe("catalog coverage gate", () => {
  it("keeps the scoped 95% floor and wires it into just web-test", () => {
    const config = readFileSync(path.join(repoRoot, "apps/web/vitest.catalog.config.ts"), "utf8");
    const justfile = readFileSync(path.join(repoRoot, "justfile"), "utf8");
    expect(config).toContain("statements: 95");
    expect(config).toContain("branches: 95");
    expect(config).toContain("functions: 95");
    expect(config).toContain("lines: 95");
    expect(config).toContain("src/lib/catalog-query.ts");
    expect(config).toContain("src/components/organisms/catalog-filter-panel.tsx");
    expect(justfile).toContain("bun run test:coverage:catalog");
    expect(justfile).toMatch(/web-test:[\s\S]*test:coverage:catalog/);
  });
});
