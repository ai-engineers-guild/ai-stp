import { describe, expect, it } from "vitest";

import { buildDocsNav, loadDocsNav } from "@/lib/docs-nav";
import {
  canonicalDocsSlug,
  docsMarkdownRedirectPath,
  hrefFromDocsSlugs,
} from "@/lib/docs-nav-path";

const ROOT_YAML = `
nav:
  - Overview: index.md
  - Quickstart: quickstart
  - Harnesses: harnesses.md
  - Concepts: concepts
  - Catalog: catalog
  - CLI: cli
  - Trust and safety:
      - Overview: trust-and-safety/index.md
      - Security checks: security-checks.md
  - Troubleshooting: troubleshooting
`;

const QUICKSTART_YAML = `
nav:
  - Overview: index.md
  - For people: human.md
  - For agents: agent.md
`;

const CLI_YAML = `
nav:
  - Overview: index.md
  - Command map: commands.md
  - Observe: observe.md
  - Component:
      - Overview: component.md
      - Discovery: component-discover.md
`;

const PAGES = [
  { slugs: ["en"], title: "Overview" },
  { slugs: ["en", "quickstart"], title: "Quickstart" },
  { slugs: ["en", "quickstart", "human"], title: "Quickstart for people" },
  { slugs: ["en", "quickstart", "agent"], title: "Quickstart for agents" },
  { slugs: ["en", "harnesses"], title: "Supported harnesses" },
  { slugs: ["en", "concepts"], title: "Concepts" },
  { slugs: ["en", "catalog"], title: "Catalog" },
  { slugs: ["en", "cli"], title: "CLI" },
  { slugs: ["en", "cli", "commands"], title: "Command map" },
  { slugs: ["en", "cli", "observe"], title: "Observe" },
  { slugs: ["en", "cli", "component"], title: "Component commands" },
  { slugs: ["en", "cli", "component-discover"], title: "Discovery" },
  { slugs: ["en", "trust-and-safety"], title: "Trust and safety" },
  { slugs: ["en", "security-checks"], title: "Security checks" },
  { slugs: ["en", "troubleshooting"], title: "Troubleshooting" },
  { slugs: ["en", "orphan-page"], title: "Orphan" },
];

describe("docs nav", () => {
  it("maps locale root slugs to /docs", () => {
    expect(hrefFromDocsSlugs(["en"])).toBe("/docs");
    expect(hrefFromDocsSlugs(["en", "quickstart", "human"])).toBe("/docs/quickstart/human");
  });

  it("strips a trailing .md from relative Markdown links", () => {
    expect(canonicalDocsSlug(["quickstart", "human.md"])).toEqual(["quickstart", "human"]);
    expect(canonicalDocsSlug(["cli", "index.md"])).toEqual(["cli"]);
    expect(canonicalDocsSlug(["index.md"])).toEqual([]);
    expect(canonicalDocsSlug(["quickstart", "human"])).toBeNull();
    expect(docsMarkdownRedirectPath("/en/docs/quickstart/human.md")).toBe(
      "/en/docs/quickstart/human",
    );
    expect(docsMarkdownRedirectPath("/ru/ai/docs/cli/index.md")).toBe("/ru/ai/docs/cli");
    expect(docsMarkdownRedirectPath("/en/docs/quickstart/human")).toBeNull();
  });

  it("nests .pages the way MkDocs does, including security-checks under trust", () => {
    const tree = buildDocsNav({
      rootYaml: ROOT_YAML,
      nestedYaml: { quickstart: QUICKSTART_YAML, cli: CLI_YAML },
      pages: PAGES,
    });
    expect(tree.map((node) => node.title)).toEqual([
      "Overview",
      "Quickstart",
      "Harnesses",
      "Concepts",
      "Catalog",
      "CLI",
      "Trust and safety",
      "Troubleshooting",
      "Orphan",
    ]);
    const quickstart = tree.find((node) => node.title === "Quickstart");
    expect(quickstart?.href).toBe("/docs/quickstart");
    expect(quickstart?.children?.map((child) => child.title)).toEqual(["For people", "For agents"]);
    const cli = tree.find((node) => node.title === "CLI");
    expect(cli?.href).toBe("/docs/cli");
    expect(cli?.children?.map((child) => child.title)).toEqual([
      "Command map",
      "Observe",
      "Component",
    ]);
    const component = cli?.children?.find((child) => child.title === "Component");
    expect(component?.href).toBeUndefined();
    expect(component?.children?.map((child) => child.href)).toEqual([
      "/docs/cli/component",
      "/docs/cli/component-discover",
    ]);
    const trust = tree.find((node) => node.title === "Trust and safety");
    expect(trust?.children?.map((child) => child.href)).toEqual([
      "/docs/trust-and-safety",
      "/docs/security-checks",
    ]);
    expect(tree.find((node) => node.title === "Catalog")?.href).toBe("/docs/catalog");
    expect(tree.find((node) => node.title === "Concepts")?.children).toBeUndefined();
  });

  it("loads the English help-center .pages from the repository", () => {
    const tree = loadDocsNav("en", [
      { slugs: ["en"], title: "Overview" },
      { slugs: ["en", "quickstart"], title: "Quickstart" },
      { slugs: ["en", "quickstart", "human"], title: "Quickstart for people" },
      { slugs: ["en", "quickstart", "agent"], title: "Quickstart for agents" },
      { slugs: ["en", "catalog"], title: "Catalog" },
      { slugs: ["en", "security-checks"], title: "Security checks" },
      { slugs: ["en", "trust-and-safety"], title: "Trust and safety" },
    ]);
    const titles = tree.map((node) => node.title);
    expect(titles[0]).toBe("Overview");
    expect(titles).toContain("Quickstart");
    expect(titles).toContain("Catalog");
    const quickstart = tree.find((node) => node.title === "Quickstart");
    expect(quickstart?.children?.map((child) => child.title)).toEqual(["For people", "For agents"]);
    const trust = tree.find((node) => node.title === "Trust and safety");
    expect(trust?.children?.some((child) => child.href === "/docs/security-checks")).toBe(true);
  });
});
