import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const webRoot = path.resolve(__dirname, "../..");
const fontsDir = path.join(webRoot, "public", "fonts");
const globalsCss = readFileSync(path.join(webRoot, "src/app/globals.css"), "utf8");

describe("self-hosted plex faces", () => {
  it("declares only files that exist under public/fonts", () => {
    const urls = [...globalsCss.matchAll(/url\(["'](\/fonts\/[^"']+)["']\)/g)].flatMap((match) =>
      match[1] === undefined ? [] : [match[1]],
    );
    expect(urls.length).toBeGreaterThanOrEqual(8);
    expect(globalsCss).not.toMatch(/url\(["']?\/fonts\/(?:Gerstner|FTSystemMono)/i);
    for (const url of urls) {
      const relative = url.replace(/^\/+/, "");
      expect(existsSync(path.join(webRoot, "public", relative))).toBe(true);
    }
    const shipped = readdirSync(fontsDir).filter((name) => name.endsWith(".woff2"));
    expect(shipped.every((name) => name.startsWith("plex-"))).toBe(true);
  });
});
