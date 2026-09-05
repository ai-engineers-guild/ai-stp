/**
 * Small, deterministic GFM renderer for published content.
 * Raw HTML never becomes executable markup; supported media is generated here.
 */

const FORBIDDEN =
  /<\s*(script|style|iframe|object|embed|form|input|img|svg)\b|javascript:|data:|(?<![a-z0-9_])on[a-z]+\s*=/i;
const LOCAL_CONTENT_IMAGE = /^\/content\/illustrations\/[a-z0-9._-]+\.(svg|png|jpg|jpeg|webp|gif)$/;
const HEADING_ID = /^[a-z0-9][a-z0-9_-]*$/i;
const TOKEN = "\u0000";

export type RenderedMarkdown = { html: string; excerpt: string };
type RenderOptions = { article?: boolean; title?: string; coverImage?: string | null };

function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function excerptFromSource(source: string): string {
  const text = source
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/<[^>]+>/g, " ")
    .replace(/[`*_#>-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return text.length <= 280 ? text : `${text.slice(0, 279).trimEnd()}…`;
}

function addToken(tokens: string[], value: string): string {
  const index = tokens.push(value) - 1;
  return `${TOKEN}${index}${TOKEN}`;
}

function restoreTokens(value: string, tokens: string[]): string {
  return value
    .split(new RegExp(`${TOKEN}(\\d+)${TOKEN}`, "g"))
    .map((part, index) => (index % 2 ? (tokens[Number(part)] ?? "") : escapeHtml(part)))
    .join("");
}

function safeLink(href: string): boolean {
  return href.startsWith("#") || /^https:\/\/[^\s)]+$/i.test(href);
}

function inline(text: string): string {
  const tokens: string[] = [];
  let value = text;
  value = value.replace(/`([^`\n]+)`/g, (_match, code: string) =>
    addToken(tokens, `<code>${escapeHtml(code)}</code>`),
  );
  value = value.replace(
    /!\[([^\]]*)\]\((\/content\/illustrations\/[^)\s]+)\)/g,
    (_match, alt: string, src: string) =>
      LOCAL_CONTENT_IMAGE.test(src)
        ? addToken(
            tokens,
            `<img src="${src}" alt="${escapeHtml(alt)}" loading="lazy" decoding="async">`,
          )
        : escapeHtml(alt),
  );
  value = value.replace(
    /\[([^\]]+)\]\(([^)\s]+)(?:\s+["']([^"']+)["'])?\)/g,
    (_match, label: string, href: string, title?: string) => {
      if (!safeLink(href)) return escapeHtml(label);
      const titleAttribute = title ? ` title="${escapeHtml(title)}"` : "";
      return addToken(
        tokens,
        `<a href="${escapeHtml(href)}"${titleAttribute} rel="noopener noreferrer">${inline(label)}</a>`,
      );
    },
  );
  value = value.replace(
    /<(u|b|strong|em)>([\s\S]*?)<\/\1>/gi,
    (_match, rawTag: string, body: string) => {
      const tag = rawTag.toLowerCase() === "b" ? "strong" : rawTag.toLowerCase();
      return addToken(tokens, `<${tag}>${inline(body)}</${tag}>`);
    },
  );
  value = value.replace(
    /\*\*([^*\n]+)\*\*|__([^_\n]+)__/g,
    (_match, bold?: string, under?: string) =>
      addToken(tokens, `<strong>${escapeHtml(bold ?? under ?? "")}</strong>`),
  );
  value = value.replace(/~~([^~\n]+)~~/g, (_match, strike: string) =>
    addToken(tokens, `<del>${escapeHtml(strike)}</del>`),
  );
  value = value.replace(
    /(?<![\w])([*_])([^*_\n]+)\1(?![\w])/g,
    (_match, _marker: string, italic: string) => addToken(tokens, `<em>${escapeHtml(italic)}</em>`),
  );
  return restoreTokens(value, tokens);
}

function headingId(title: string, ids: Set<string>, explicit?: string): string {
  const clean = encodeURIComponent(title)
    .replace(/%[0-9a-f]{2}/gi, "-")
    .toLowerCase()
    .trim();
  const generated = clean
    .normalize("NFKD")
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-|-$/g, "");
  const base = explicit && HEADING_ID.test(explicit) ? explicit : generated || "section";
  let id = base;
  let suffix = 2;
  while (ids.has(id)) id = `${base}-${suffix++}`;
  ids.add(id);
  return id;
}

function tableCells(line: string): string[] {
  const source = line.trim().replace(/^\||\|$/g, "");
  const cells: string[] = [];
  let cell = "";
  let escaped = false;
  for (const char of source) {
    if (char === "|" && !escaped) {
      cells.push(cell.trim());
      cell = "";
    } else cell += char;
    escaped = char === "\\" && !escaped;
    if (char !== "\\") escaped = false;
  }
  cells.push(cell.trim());
  return cells.map((item) => item.replaceAll("\\|", "|"));
}

function isTableSeparator(line: string): boolean {
  const cells = tableCells(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function tableHtml(lines: string[]): string {
  const headers = tableCells(lines[0] ?? "");
  const separators = tableCells(lines[1] ?? "");
  const alignments = separators.map((cell) =>
    cell.startsWith(":") && cell.endsWith(":")
      ? "center"
      : cell.endsWith(":")
        ? "right"
        : cell.startsWith(":")
          ? "left"
          : "",
  );
  const cells = (row: string[], tag: "th" | "td") =>
    headers
      .map((_header, index) => {
        const align = alignments[index] ? ` style="text-align:${alignments[index]}"` : "";
        return `<${tag}${align}>${inline(row[index] ?? "")}</${tag}>`;
      })
      .join("");
  const rows = lines
    .slice(2)
    .map((line) => `<tr>${cells(tableCells(line), "td")}</tr>`)
    .join("");
  return `<div class="article-table"><table><thead><tr>${cells(headers, "th")}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function videoHtml(kind: string, href: string): string | null {
  try {
    const url = new URL(href);
    const host = url.hostname.toLowerCase();
    let id = "";
    if (kind === "youtube" && ["youtube.com", "www.youtube.com", "youtu.be"].includes(host)) {
      id =
        host === "youtu.be"
          ? url.pathname.slice(1)
          : (url.searchParams.get("v") ?? url.pathname.split("/").pop() ?? "");
      if (!/^[A-Za-z0-9_-]{6,}$/u.test(id)) return null;
      return `<figure class="article-video"><div class="article-video__frame"><iframe src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}" title="Embedded YouTube video" loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe></div><figcaption><a href="${escapeHtml(href)}" rel="noopener noreferrer">Open video</a></figcaption></figure>`;
    }
    if (kind === "vimeo" && ["vimeo.com", "www.vimeo.com", "player.vimeo.com"].includes(host)) {
      id = url.pathname.split("/").filter(Boolean).pop() ?? "";
      if (!/^\d{1,12}$/u.test(id)) return null;
      return `<figure class="article-video"><div class="article-video__frame"><iframe src="https://player.vimeo.com/video/${id}" title="Embedded Vimeo video" loading="lazy" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe></div><figcaption><a href="${escapeHtml(href)}" rel="noopener noreferrer">Open video</a></figcaption></figure>`;
    }
  } catch {
    return null;
  }
  return null;
}

// eslint-disable-next-line complexity -- one linear pass keeps nested Markdown deterministic.
function renderList(lines: string[], start: number): { html: string; next: number } {
  const first = lines[start]?.match(/^(\s*)([-*+]\s+|\d+[.)]\s+)(.*)$/u);
  if (!first) return { html: "", next: start };
  const baseIndent = first[1]?.length ?? 0;
  const ordered = /^\d/u.test(first[2] ?? "");
  const tag = ordered ? "ol" : "ul";
  const items: string[] = [];
  let index = start;
  while (index < lines.length) {
    const match = lines[index]?.match(/^(\s*)([-*+]\s+|\d+[.)]\s+)(.*)$/u);
    if (!match || (match[1]?.length ?? 0) !== baseIndent || /^\d/u.test(match[2] ?? "") !== ordered)
      break;
    const content = [match[3] ?? ""];
    index += 1;
    let nested = "";
    while (index < lines.length) {
      const nestedMatch = lines[index]?.match(/^(\s*)([-*+]\s+|\d+[.)]\s+)(.*)$/u);
      if (nestedMatch && (nestedMatch[1]?.length ?? 0) > baseIndent) {
        const result = renderList(lines, index);
        nested += result.html;
        index = result.next;
        continue;
      }
      const continuation = lines[index]?.match(/^\s+(.*)$/u);
      if (continuation && !nestedMatch && !lines[index]?.trim().startsWith("#")) {
        content.push(continuation[1] ?? "");
        index += 1;
        continue;
      }
      break;
    }
    items.push(`<li>${inline(content.join(" "))}${nested}</li>`);
    if (lines[index]?.trim() === "") break;
  }
  return { html: `<${tag}>${items.join("")}</${tag}>`, next: index };
}

function isBlockStart(line: string): boolean {
  return /^(?:#{1,6}\s+|```|~~~|>\s?|[-*+]\s+|\d+[.)]\s+|\|.*\|\s*$|@\[(?:youtube|vimeo)\]\()/u.test(
    line.trim(),
  );
}

function stripArticleChrome(source: string, options: RenderOptions): string {
  if (!options.article || !options.title) return source;

  const normalize = (value: string) =>
    value
      .replace(/[`*_~]/g, "")
      .trim()
      .toLocaleLowerCase();
  const lines = source.replaceAll("\r\n", "\n").split("\n");
  let index = 0;
  while (index < lines.length && !lines[index]?.trim()) index += 1;

  const heading = lines[index]?.trim().match(/^#\s+(.+?)(?:\s+\{#[^\s}]+\})?\s*$/u);
  if (!heading || normalize(heading[1] ?? "") !== normalize(options.title)) return source;
  index += 1;
  while (index < lines.length && !lines[index]?.trim()) index += 1;

  const image = lines[index]?.trim().match(/^!\[[^\]]*\]\(([^)\s]+)\)$/u);
  if (options.coverImage && image?.[1] === options.coverImage) {
    index += 1;
    while (index < lines.length && !lines[index]?.trim()) index += 1;
  }
  return lines.slice(index).join("\n");
}

// eslint-disable-next-line complexity -- block grammar is intentionally kept in one safe parser.
function renderBlocks(lines: string[], ids: Set<string>, article: boolean): string {
  const blocks: string[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index] ?? "";
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }
    const fence = trimmed.match(/^(`{3,}|~{3,})([\w-]*)$/u);
    if (fence) {
      const marker = fence[1] ?? "```";
      const code: string[] = [];
      index += 1;
      const fenceChar = marker.startsWith("~") ? "~" : "`";
      while (index < lines.length && !lines[index]?.trim().startsWith(fenceChar.repeat(3))) {
        code.push(lines[index] ?? "");
        index += 1;
      }
      if (index < lines.length) index += 1;
      const language = fence[2] ? ` class="language-${escapeHtml(fence[2])}"` : "";
      blocks.push(`<pre><code${language}>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }
    if (trimmed === "<details>") {
      const close = lines.findIndex(
        (candidate, candidateIndex) => candidateIndex > index && candidate.trim() === "</details>",
      );
      const end = close < 0 ? lines.length : close;
      const inner = lines.slice(index + 1, end);
      const summaryIndex = inner.findIndex((candidate) => candidate.trim().startsWith("<summary>"));
      const summary =
        summaryIndex >= 0
          ? (inner[summaryIndex] ?? "").trim().replace(/^<summary>|<\/summary>$/g, "")
          : "Details";
      const content = summaryIndex >= 0 ? inner.slice(summaryIndex + 1) : inner;
      blocks.push(
        `<details><summary>${inline(summary)}</summary>${renderBlocks(content, ids, article)}</details>`,
      );
      index = close < 0 ? lines.length : close + 1;
      continue;
    }
    const video = trimmed.match(/^@\[(youtube|vimeo)\]\((https:\/\/[^)\s]+)\)$/u);
    if (video) {
      blocks.push(videoHtml(video[1] ?? "", video[2] ?? "") ?? `<p>${inline(trimmed)}</p>`);
      index += 1;
      continue;
    }
    const heading = trimmed.match(/^(#{1,6})\s+(.+?)(?:\s+\{#([^\s}]+)\})?$/u);
    if (heading) {
      const title = heading[2] ?? "";
      const level = article
        ? (heading[1]?.length ?? 1)
        : Math.min((heading[1]?.length ?? 1) + 1, 6);
      const id = headingId(title, ids, heading[3]);
      blocks.push(`<h${level} id="${escapeHtml(id)}">${escapeHtml(title)}</h${level}>`);
      index += 1;
      continue;
    }
    if (/^(?:\*\s*){3,}$|^(?:-\s*){3,}$|^(?:_\s*){3,}$/u.test(trimmed)) {
      blocks.push("<hr>");
      index += 1;
      continue;
    }
    if (trimmed.startsWith(">")) {
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/u.test(lines[index] ?? "")) {
        quote.push((lines[index] ?? "").replace(/^>\s?/u, ""));
        index += 1;
      }
      blocks.push(`<blockquote>${renderBlocks(quote, ids, article)}</blockquote>`);
      continue;
    }
    if (
      index + 1 < lines.length &&
      line.includes("|") &&
      isTableSeparator(lines[index + 1] ?? "")
    ) {
      const table = [line, lines[index + 1] ?? ""];
      index += 2;
      while (index < lines.length && (lines[index] ?? "").includes("|"))
        table.push(lines[index++] ?? "");
      blocks.push(tableHtml(table));
      continue;
    }
    if (/^\s*(?:[-*+]\s+|\d+[.)]\s+)/u.test(line)) {
      const result = renderList(lines, index);
      blocks.push(result.html);
      index = result.next;
      continue;
    }
    const paragraph: string[] = [trimmed];
    index += 1;
    while (index < lines.length && lines[index]?.trim() && !isBlockStart(lines[index] ?? "")) {
      paragraph.push((lines[index] ?? "").trim());
      index += 1;
    }
    blocks.push(`<p>${inline(paragraph.join(" "))}</p>`);
  }
  return blocks.join("");
}

export function renderMarkdownOnServer(
  source: string,
  options: RenderOptions = {},
): RenderedMarkdown {
  const excerpt = excerptFromSource(source);
  if (FORBIDDEN.test(source))
    return { html: excerpt ? `<p>${escapeHtml(excerpt)}</p>` : "", excerpt };
  const renderSource = stripArticleChrome(source, options);
  return {
    html: renderBlocks(
      renderSource.replaceAll("\r\n", "\n").split("\n"),
      new Set(),
      options.article ?? false,
    ),
    excerpt,
  };
}

export function excerptMarkdown(source: string): string {
  return excerptFromSource(source);
}
