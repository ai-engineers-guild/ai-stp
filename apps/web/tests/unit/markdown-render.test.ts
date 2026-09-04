import { describe, expect, it } from "vitest";

import { excerptMarkdown, renderMarkdownOnServer } from "@/lib/markdown/render";

describe("renderMarkdownOnServer", () => {
  it("renders safe subset with noopener links", () => {
    const ok = renderMarkdownOnServer(
      "Hello **world** and `code` with [link](https://example.com/a)",
    );
    expect(ok.html).toContain("<strong>world</strong>");
    expect(ok.html).toContain('rel="noopener noreferrer"');
    expect(ok.html).toContain("<code>code</code>");
    expect(ok.excerpt).toContain("Hello");
  });

  it("does not emit script tags for malicious input", () => {
    const bad = renderMarkdownOnServer("x <script>alert(1)</script>");
    expect(bad.html.toLowerCase()).not.toContain("<script");
  });

  it("renders fenced code without executing content", () => {
    const rendered = renderMarkdownOnServer("```\nls -la\n```\n\nAfter");
    expect(rendered.html).toContain("<pre><code>");
    expect(rendered.html).toContain("ls -la");
  });

  it("bounds excerpts deterministically", () => {
    const long = "word ".repeat(200);
    const a = excerptMarkdown(long);
    const b = excerptMarkdown(long);
    expect(a).toBe(b);
    expect(a.length).toBeLessThanOrEqual(280);
  });

  it("renders headings, tables, emoji, and annotated links", () => {
    const rendered = renderMarkdownOnServer(
      '## Matrix 🚀\n\n| Harness | State |\n| --- | --- |\n| Codex | Ready |\n\n[Docs](https://example.com/docs "Reference")',
    );
    expect(rendered.html).toContain("<h3>Matrix 🚀</h3>");
    expect(rendered.html).toContain("<table>");
    expect(rendered.html).toContain("<th>Harness</th>");
    expect(rendered.html).toContain('title="Reference"');
  });

  it("handles every heading level, paragraphs, and incomplete table syntax", () => {
    const rendered = renderMarkdownOnServer(
      "# H1\n\n## H2\n\n### H3\n\n#### H4\n\n##### H5\n\n###### H6\n\nplain\nnext\n\n| not | a table |",
    );
    expect(rendered.html).toContain("<h2>H1</h2>");
    expect(rendered.html).toContain("<h3>H2</h3>");
    expect(rendered.html).toContain("<h4>H3</h4>");
    expect(rendered.html).toContain("<p>plain next</p>");
    expect(rendered.html).not.toContain("<table>");
  });

  it("does not turn unsafe or malformed URLs into anchors", () => {
    const rendered = renderMarkdownOnServer(
      "[script](javascript:alert(1)) [relative](/private) [broken](https://example.com",
    );
    expect(rendered.html).not.toContain("javascript:");
    expect(rendered.html).not.toContain('href="/private"');
  });

  it("renders unordered and ordered lists", () => {
    const rendered = renderMarkdownOnServer("- one\n- **two**\n\n1. first\n2. `second`");

    expect(rendered.html).toContain("<ul>");
    expect(rendered.html).toContain("<ol>");
    expect(rendered.html).toContain("<strong>two</strong>");
    expect(rendered.html).toContain("<code>second</code>");
  });

  it("rejects illustration paths outside the allowlist", () => {
    const rendered = renderMarkdownOnServer("![skip](/content/illustrations/NOT.svg)");
    expect(rendered.html).not.toContain("<img");
    expect(rendered.html).toContain("skip");
  });

  it("renders only allowlisted local content illustrations", () => {
    const svg = renderMarkdownOnServer("![Skill package](/content/illustrations/kind-skill.svg)");
    const png = renderMarkdownOnServer("![Skill package](/content/illustrations/kind-skill.png)");
    const jpg = renderMarkdownOnServer("![Skill package](/content/illustrations/kind-skill.jpg)");
    const remote = renderMarkdownOnServer("![Tracking pixel](https://example.com/pixel.svg)");

    expect(svg.html).toContain(
      '<img src="/content/illustrations/kind-skill.svg" alt="Skill package"',
    );
    expect(png.html).toContain(
      '<img src="/content/illustrations/kind-skill.png" alt="Skill package"',
    );
    expect(jpg.html).toContain(
      '<img src="/content/illustrations/kind-skill.jpg" alt="Skill package"',
    );
    expect(remote.html).not.toContain("<img");
    expect(remote.html).toContain("Tracking pixel");
  });

  it("renders fragment links, aligned tables, and empty input", () => {
    const rendered = renderMarkdownOnServer(
      "[Section](#section)\n\n| Left | Right |\n| :--- | ---: |\n| a | b |",
    );
    expect(rendered.html).toContain('href="#section"');
    expect(rendered.html).toContain("<td>a</td><td>b</td>");
    expect(renderMarkdownOnServer("\n\n")).toEqual({ html: "", excerpt: "" });
  });

  it("keeps invalid table separators and mixed list blocks as paragraphs", () => {
    const rendered = renderMarkdownOnServer(
      "| A | B |\n| -- | nope |\n| x | y |\n\n- list\nplain\n\n1. item\nplain",
    );
    expect(rendered.html).not.toContain("<table>");
    expect(rendered.html).not.toContain("<ul>");
    expect(rendered.html).not.toContain("<ol>");
  });
});
