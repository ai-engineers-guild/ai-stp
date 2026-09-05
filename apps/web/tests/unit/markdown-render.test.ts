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
    expect(rendered.html).toContain(
      '<td style="text-align:left">a</td><td style="text-align:right">b</td>',
    );
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

  it("omits shell-owned article title and cover from the body", () => {
    const rendered = renderMarkdownOnServer(
      "# Codex\n\n![(Codex) profile](/content/illustrations/setup-codex.jpg)\n\nIntro\n\n## Native surface",
      { article: true, title: "Codex", coverImage: "/content/illustrations/setup-codex.jpg" },
    );

    expect(rendered.html).not.toContain('<h1 id="codex">Codex</h1>');
    expect(rendered.html).not.toContain("setup-codex.jpg");
    expect(rendered.html).toContain("<p>Intro</p>");
    expect(rendered.html).toContain('<h2 id="native-surface">Native surface</h2>');
  });

  it("embeds only supported video hosts and keeps the source link", () => {
    const rendered = renderMarkdownOnServer(
      "@[youtube](https://www.youtube.com/watch?v=dQw4w9WgXcQ)\n\n@[vimeo](https://vimeo.com/12345678)",
      { article: true },
    );
    expect(rendered.html).toContain("youtube-nocookie.com/embed/dQw4w9WgXcQ");
    expect(rendered.html).toContain("player.vimeo.com/video/12345678");
    expect(rendered.html).toContain('href="https://www.youtube.com/watch?v=dQw4w9WgXcQ"');
    expect(
      renderMarkdownOnServer("@[youtube](https://evil.example/video/12345678)").html,
    ).not.toContain("<iframe");
  });

  it("covers inline fallbacks, generated ids, and every table alignment", () => {
    const rendered = renderMarkdownOnServer(
      "# !!!\n\n# !!!\n\n## Title {#bad id}\n\n**bold** __under__ ~~gone~~ *italic* _also_ <b>tag</b> <em>em</em>\n\n`code` ![ok](/content/illustrations/ok.gif) [fragment](#section) [unsafe](http://example.com)\n\n| Center | Right | Left | Plain |\n| :---: | ---: | :--- | --- |\n| a\\|b | c | d | e |\n| short |",
    );
    expect(rendered.html).toContain('id="section"');
    expect(rendered.html).toContain('style="text-align:center"');
    expect(rendered.html).toContain('style="text-align:right"');
    expect(rendered.html).toContain('style="text-align:left"');
    expect(rendered.html).toContain("a|b");
    expect(rendered.html).not.toContain('href="http://example.com"');
    expect(renderMarkdownOnServer("\u0000999\u0000").html).toBe("<p></p>");
  });

  it("covers rejected video variants and article chrome edge cases", () => {
    const rendered = renderMarkdownOnServer(
      "@[youtube](https://youtu.be/valid123)\n\n@[youtube](https://youtube.com/watch?v=valid123)\n\n@[youtube](https://youtube.com/embed/valid123)\n\n@[youtube](https://youtube.com/watch)\n\n@[vimeo](https://www.vimeo.com/123)\n\n@[vimeo](https://player.vimeo.com/video/123)\n\n@[vimeo](https://vimeo.com/nope)",
      { article: true, title: "Different", coverImage: "/content/illustrations/other.jpg" },
    );
    expect(rendered.html).toContain("youtube-nocookie.com/embed/valid123");
    expect(rendered.html).toContain("player.vimeo.com/video/123");
    expect(
      renderMarkdownOnServer("@[vimeo](https://evil.example/123456)", { article: true }).html,
    ).not.toContain("<iframe");

    const withoutCover = renderMarkdownOnServer(
      "# Title\r\n\r\n![](https://example.com/cover.jpg)\r\n\r\nBody",
      { article: true, title: "Title", coverImage: "/content/illustrations/cover.jpg" },
    );
    expect(withoutCover.html).toContain("Body");
    expect(
      renderMarkdownOnServer("@[vimeo](https://vimeo.com/)", { article: true }).html,
    ).not.toContain("<iframe");
    expect(
      renderMarkdownOnServer("\n\n# Title\n\nBody", { article: true, title: "Title" }).html,
    ).toContain("Body");
    expect(renderMarkdownOnServer("Body", { article: true, title: "Title" }).html).toContain(
      "Body",
    );
  });

  it("covers fenced blocks, details, quotes, lists, and article title removal", () => {
    const rendered = renderMarkdownOnServer(
      "~~~ts\nconst x = 1\n~~~\n\n<details>\n<summary>More</summary>\ninside\n</details>\n\n<details>\nwithout summary\n</details>\n\n<details>\nunclosed\n\n> first\n> second\n\n- parent\n  continuation\n  - child\n- next\n1. mixed\n\n1. one\n2. two\n\n---\n***\n___",
      { article: true, title: "Not present" },
    );
    expect(rendered.html).toContain('class="language-ts"');
    expect(rendered.html).toContain("<summary>More</summary>");
    expect(rendered.html).toContain("<summary>Details</summary>");
    expect(rendered.html).toContain("<blockquote>");
    expect(rendered.html).toContain("continuation");
    expect(rendered.html).toContain("<ol>");
    expect(rendered.html).toContain("<hr>");

    const stripped = renderMarkdownOnServer("# Title\n\nBody", { article: true, title: "Title" });
    expect(stripped.html).toBe("<p>Body</p>");
    expect(renderMarkdownOnServer("<script>").html).toBe("");
    expect(renderMarkdownOnServer("plain").html).toBe("<p>plain</p>");
  });
});
