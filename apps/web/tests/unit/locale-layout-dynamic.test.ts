import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const webSrc = path.resolve(__dirname, "../../src");

describe("locale layout dynamic boundary", () => {
  it("does not declare a global force-dynamic on the locale layout", () => {
    const source = readFileSync(path.join(webSrc, "app/[locale]/layout.tsx"), "utf8");
    expect(source).not.toMatch(/dynamic\s*=\s*["']force-dynamic["']/);
    expect(source).toContain("readProjection");
    expect(source).toContain("readCanonicalPathname");
    expect(source).toContain("SPEC-036");
  });

  it("keeps mutation revalidatePath for public catalog convergence", () => {
    const presentation = readFileSync(path.join(webSrc, "actions/object-presentation.ts"), "utf8");
    const products = readFileSync(path.join(webSrc, "actions/external-products.ts"), "utf8");
    expect(presentation).toContain("revalidatePath(`/${parsed.data.locale}/catalog`)");
    expect(products).toContain("revalidatePath(`/${parsed.data.locale}/catalog`)");
  });

  it("routes catalog reads through publicApiGet and leaves account reads private", () => {
    const catalog = readFileSync(path.join(webSrc, "lib/api/catalog.ts"), "utf8");
    const account = readFileSync(path.join(webSrc, "lib/api/account.ts"), "utf8");
    const profile = readFileSync(path.join(webSrc, "lib/api/public-profile.ts"), "utf8");
    expect(catalog).toContain("publicApiGet");
    expect(catalog).not.toContain('from "@/lib/api/http"');
    expect(account).toContain('from "@/lib/api/http"');
    expect(account).not.toContain("publicApiGet");
    expect(profile).toContain("publicApiGet");
    expect(profile).toContain('from "@/lib/api/http"');
    expect(profile).toMatch(/readPublisherProfile[\s\S]*publicApiGet/);
  });
});
