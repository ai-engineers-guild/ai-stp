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
    expect(rendered.html).toContain('<h3 id="matrix">Matrix 🚀</h3>');
    expect(rendered.html).toContain("<table>");
    expect(rendered.html).toContain("<th>Harness</th>");
    expect(rendered.html).toContain('title="Reference"');
  });

  it("handles every heading level, paragraphs, and incomplete table syntax", () => {
    const rendered = renderMarkdownOnServer(
      "# H1\n\n## H2\n\n### H3\n\n#### H4\n\n##### H5\n\n###### H6\n\nplain\nnext\n\n| not | a table |",
    );
    expect(rendered.html).toContain('<h2 id="h1">H1</h2>');
    expect(rendered.html).toContain('<h3 id="h2">H2</h3>');
    expect(rendered.html).toContain('<h4 id="h3">H3</h4>');
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
    expect(rendered.html).toContain('<td style="text-align:left">a</td><td style="text-align:right">b</td>');
    expect(renderMarkdownOnServer("\n\n")).toEqual({ html: "", excerpt: "" });
  });

  it("keeps invalid table separators as paragraphs and renders separate lists", () => {
    const rendered = renderMarkdownOnServer(
      "| A | B |\n| -- | nope |\n| x | y |\n\n- list\nplain\n\n1. item\nplain",
    );
    expect(rendered.html).not.toContain("<table>");
    expect(rendered.html).toContain("<ul>");
    expect(rendered.html).toContain("<ol>");
  });

  it("keeps common editorial structure from imported articles", () => {
    const rendered = renderMarkdownOnServer(
      "> A useful warning.\n\n---\n\n<u>important</u> and ~~obsolete~~",
    );
    expect(rendered.html).toContain("<blockquote>");
    expect(rendered.html).toContain("<hr>");
    expect(rendered.html).toContain("<u>important</u>");
    expect(rendered.html).toContain("<del>obsolete</del>");
  });

  it("renders article heading levels, anchors, emphasis, and nested lists", () => {
    const rendered = renderMarkdownOnServer(
      "# Title {#intro}\n\n## Subsection\n\n### Detail\n\n#### Note\n\n[Intro](#intro)\n\n**bold** *italic* __bold__ _italic_ <u>under</u> ~~gone~~\n\n- parent\n  - child\n  - **bold child**\n1. first\n   1. nested",
      { article: true },
    );
    expect(rendered.html).toContain('<h1 id="intro">Title</h1>');
    expect(rendered.html).toContain('<h2 id="subsection">Subsection</h2>');
    expect(rendered.html).toContain('<h3 id="detail">Detail</h3>');
    expect(rendered.html).toContain('<h4 id="note">Note</h4>');
    expect(rendered.html).toContain("<strong>bold</strong>");
    expect(rendered.html).toContain("<em>italic</em>");
    expect(rendered.html).toContain("<u>under</u>");
    expect(rendered.html).toContain("<del>gone</del>");
    expect(rendered.html).toContain("<ul><li>parent<ul>");
    expect(rendered.html).toContain("<ol><li>first<ol>");
    expect(rendered.html).toContain('href="#intro"');
  });

  it("embeds only supported video hosts and keeps the source link", () => {
    const rendered = renderMarkdownOnServer(
      "@[youtube](https://www.youtube.com/watch?v=dQw4w9WgXcQ)\n\n@[vimeo](https://vimeo.com/12345678)",
      { article: true },
    );
    expect(rendered.html).toContain("youtube-nocookie.com/embed/dQw4w9WgXcQ");
    expect(rendered.html).toContain("player.vimeo.com/video/12345678");
    expect(rendered.html).toContain('href="https://www.youtube.com/watch?v=dQw4w9WgXcQ"');
    expect(renderMarkdownOnServer("@[youtube](https://evil.example/video/12345678)").html).not.toContain("<iframe");
  });
});
