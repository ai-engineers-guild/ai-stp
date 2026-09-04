/**
 * Server-side Markdown consumer for web.
 * Keeps a deterministic subset aligned with packages/contracts safe_markdown.
 */

const FORBIDDEN =
  /<\s*(script|style|iframe|object|embed|form|input|img|svg)\b|javascript:|data:|on\w+\s*=/i;
const LOCAL_CONTENT_IMAGE = /^\/content\/illustrations\/[a-z0-9-]+\.(svg|png|jpg)$/;

export type RenderedMarkdown = {
  html: string;
  excerpt: string;
};

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
    .replace(/[`*_#>-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length <= 280) return text;
  return `${text.slice(0, 279).trimEnd()}…`;
}

function inline(text: string): string {
  let out = text;
  out = out.replace(
    /!\[([^\]]*)\]\((\/content\/illustrations\/[^)\s]+)\)/g,
    (_m, alt: string, src: string) =>
      LOCAL_CONTENT_IMAGE.test(src)
        ? `<img src="${src}" alt="${escapeHtml(alt)}" loading="lazy" decoding="async">`
        : escapeHtml(alt),
  );
  out = out.replace(
    /\[([^\]]+)\]\((https:\/\/[^\s)]+|#[^\s)]*)(?:\s+["']([^"']+)["'])?\)/g,
    (_m, label: string, href: string, title?: string) =>
      `<a href="${escapeHtml(href)}"${title ? ` title="${escapeHtml(title)}"` : ""} rel="noopener noreferrer">${escapeHtml(label)}</a>`,
  );
  out = out.replace(/`([^`]+)`/g, (_m, code: string) => `<code>${escapeHtml(code)}</code>`);
  out = out.replace(
    /\*\*([^*]+)\*\*/g,
    (_m, bold: string) => `<strong>${escapeHtml(bold)}</strong>`,
  );
  return out
    .split(/(<\/?(?:a|code|strong)\b[^>]*>|<img\b[^>]*>)/g)
    .map((part) => (part.startsWith("<") ? part : escapeHtml(part)))
    .join("");
}

/** Validate and render limited Markdown for display. */
export function renderMarkdownOnServer(source: string): RenderedMarkdown {
  if (FORBIDDEN.test(source)) {
    return {
      html: `<p>${escapeHtml(excerptFromSource(source))}</p>`,
      excerpt: excerptFromSource(source),
    };
  }
  const fences: string[] = [];
  const body = source.replace(/```[\w-]*\n([\s\S]*?)```/g, (_m, code: string) => {
    fences.push(`<pre><code>${escapeHtml(code.replace(/\n$/, ""))}</code></pre>`);
    return `\n@@FENCE${fences.length - 1}@@\n`;
  });
  const parts: string[] = [];
  for (const block of body.split(/\n\s*\n/)) {
    const trimmed = block.trim();
    if (!trimmed) continue;
    const fence = trimmed.match(/^@@FENCE(\d+)@@$/);
    if (fence) {
      const idx = Number(fence[1]);
      const fenceHtml = Number.isFinite(idx) ? fences[idx] : undefined;
      if (fenceHtml) parts.push(fenceHtml);
      continue;
    }
    const lines = trimmed.split("\n");
    if (isTable(lines)) {
      const headers = tableCells(lines[0] ?? "");
      const rows = lines.slice(2).map(tableCells);
      parts.push(
        `<table><thead><tr>${headers.map((cell) => `<th>${inline(cell)}</th>`).join("")}</tr></thead>` +
          `<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${inline(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`,
      );
      continue;
    }
    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading && !trimmed.includes("\n")) {
      const hashes = heading[1] ?? "#";
      const title = heading[2] ?? "";
      const level = Math.min(hashes.length, 3) + 1;
      parts.push(`<h${level}>${inline(title)}</h${level}>`);
      continue;
    }
    if (lines.every((line) => /^[-*]\s+/.test(line))) {
      parts.push(
        `<ul>${lines.map((line) => `<li>${inline(line.replace(/^[-*]\s+/, ""))}</li>`).join("")}</ul>`,
      );
      continue;
    }
    if (lines.every((line) => /^\d+\.\s+/.test(line))) {
      parts.push(
        `<ol>${lines.map((line) => `<li>${inline(line.replace(/^\d+\.\s+/, ""))}</li>`).join("")}</ol>`,
      );
      continue;
    }
    parts.push(`<p>${inline(trimmed.replace(/\n/g, " "))}</p>`);
  }
  return { html: parts.join(""), excerpt: excerptFromSource(source) };
}

function tableCells(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isTable(lines: string[]): boolean {
  if (lines.length < 2 || !lines[0]?.includes("|")) return false;
  const separators = tableCells(lines[1] ?? "");
  return separators.length > 0 && separators.every((cell) => /^:?-{3,}:?$/.test(cell));
}

export function excerptMarkdown(source: string): string {
  return excerptFromSource(source);
}
