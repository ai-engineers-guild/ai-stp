import { readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  COMPONENT_TYPES,
  PAGE_INVENTORY,
  PAGE_INVENTORY_PATTERNS,
  pageFileToPattern,
} from "@/lib/projection/inventory";
import { MACHINE_ROUTE_PATTERNS } from "@/lib/projection/registry";

const here = path.dirname(fileURLToPath(import.meta.url));
const siteRoot = path.resolve(here, "../../src/app/[locale]/(site)");

function listPageFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      out.push(...listPageFiles(full));
      continue;
    }
    if (name === "page.tsx") {
      out.push(full);
    }
  }
  return out;
}

describe("machine route inventory (REQ-3622)", () => {
  it("pairs every human page.tsx with a machine route pattern", () => {
    const files = listPageFiles(siteRoot);
    const fromFiles = files.map((file) => pageFileToPattern(path.relative(siteRoot, file))).sort();
    expect(fromFiles).toEqual([...PAGE_INVENTORY_PATTERNS].sort());
    expect(new Set(MACHINE_ROUTE_PATTERNS)).toEqual(new Set(PAGE_INVENTORY_PATTERNS));
  });

  it("marks session access on every private workspace route", () => {
    const privatePatterns = PAGE_INVENTORY.filter((entry) => entry.access === "session").map(
      (entry) => entry.pattern,
    );
    expect(privatePatterns).toEqual(
      expect.arrayContaining([
        "account",
        "devices",
        "objects",
        "objects/:kind/:stableId",
        "publications/:planId",
        "invitations/:invitationId",
        "staff/reports/:caseId",
      ]),
    );
  });

  it("lists the eight contract component types", () => {
    expect([...COMPONENT_TYPES]).toEqual([
      "instruction",
      "skill",
      "mcp",
      "hook",
      "command",
      "agent",
      "plugin",
      "setting",
    ]);
  });
});
