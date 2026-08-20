import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const webRoot = path.resolve(__dirname, "../..");

describe("removed projection cosmetics (REQ-3613)", () => {
  it("does not ship the client projection provider or copy bridge", () => {
    expect(
      existsSync(path.join(webRoot, "src/components/providers/projection-mode-provider.tsx")),
    ).toBe(false);
    expect(
      existsSync(path.join(webRoot, "src/components/molecules/machine-projection-bridge.tsx")),
    ).toBe(false);
  });

  it("does not style machine projection via generated content rules", () => {
    const css = readFileSync(path.join(webRoot, "src/app/globals.css"), "utf8");
    expect(css).not.toContain(".machine [data-machine-projection]");
    expect(css).not.toMatch(/a\[href\]::after\s*\{[^}]*content:/s);
    expect(css).not.toContain('content: "]("');
  });

  it("does not keep localStorage projection keys in providers", () => {
    const providers = readFileSync(
      path.join(webRoot, "src/components/providers/app-providers.tsx"),
      "utf8",
    );
    expect(providers).not.toContain("ProjectionModeProvider");
    expect(providers).not.toContain("ai_stp_projection_mode");
  });

  it("keeps the human tree free of projection branches (REQ-3612)", () => {
    // Projections live in separate route trees. A `readProjection` call inside
    // a human page means the old in-page branching is creeping back.
    const siteRoot = path.join(webRoot, "src/app/[locale]/(site)");
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir)) {
        const full = path.join(dir, entry);
        if (statSync(full).isDirectory()) {
          walk(full);
        } else if (entry.endsWith(".tsx")) {
          if (readFileSync(full, "utf8").includes("readProjection")) {
            offenders.push(path.relative(siteRoot, full));
          }
        }
      }
    };
    walk(siteRoot);
    expect(offenders).toEqual([]);
  });

  it("serves the machine projection from its own route segment (REQ-3602)", () => {
    expect(existsSync(path.join(webRoot, "src/app/[locale]/ai/layout.tsx"))).toBe(true);
    expect(existsSync(path.join(webRoot, "src/app/[locale]/ai/[[...path]]/page.tsx"))).toBe(true);
    expect(existsSync(path.join(webRoot, "src/app/[locale]/(site)/layout.tsx"))).toBe(true);
    const middleware = readFileSync(path.join(webRoot, "src/middleware.ts"), "utf8");
    expect(middleware).not.toContain("NextResponse.rewrite");
  });
});
