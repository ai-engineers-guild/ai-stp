import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { expect, it } from "vitest";

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const file = path.join(dir, entry);
    return statSync(file).isDirectory() ? walk(file) : [file];
  });
}

it("keeps one shared back control per route that exposes back navigation", () => {
  const root = path.resolve(__dirname, "../../src");
  const offenders = walk(root)
    .filter((file) => file.endsWith(".tsx"))
    .filter((file) => !file.endsWith(`${path.sep}history-back-button.tsx`))
    .filter((file) => {
      const source = readFileSync(file, "utf8");
      return source.includes("HistoryBackButton");
    })
    .filter((file) => {
      const source = readFileSync(file, "utf8");
      return (source.match(/<HistoryBackButton\b/g) ?? []).length !== 1;
    })
    .map((file) => path.relative(root, file).replaceAll("\\", "/"));

  expect(offenders).toEqual([]);
});

it("does not render a second parent link beside the corporate resource back control", () => {
  const file = path.resolve(
    __dirname,
    "../../src/app/[locale]/(site)/corporate/[resource]/[resourceId]/page.tsx",
  );
  const source = readFileSync(file, "utf8");
  expect(source).toContain("const backLabel");
  expect(source).toContain("<HistoryBackButton label={backLabel} fallback={parentHref} />");
  expect(source).not.toContain("<Link\n          href={parentHref}");
});
