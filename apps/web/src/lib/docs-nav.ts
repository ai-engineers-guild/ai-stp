import { readdirSync, readFileSync, type Dirent } from "node:fs";
import path from "node:path";

import { JSON_SCHEMA, load } from "js-yaml";

import { hrefFromDocsSlugs } from "@/lib/docs-nav-path";

export {
  canonicalDocsSlug,
  docsMarkdownRedirectPath,
  hrefFromDocsSlugs,
} from "@/lib/docs-nav-path";

export type DocsNavNode = {
  title: string;
  href?: string;
  children?: DocsNavNode[];
};

export type DocsNavPage = {
  slugs: readonly string[];
  title: string;
};

type Ctx = {
  dir: string;
  nestedYaml: Readonly<Record<string, string>>;
  hrefs: ReadonlySet<string>;
  titles: ReadonlyMap<string, string>;
};

const userFacingRoot = process.env.AI_STP_USER_FACING_ROOT
  ? process.env.AI_STP_USER_FACING_ROOT
  : path.resolve(process.cwd(), "..", "..", "docs-user-facing");

export function buildDocsNav(input: {
  rootYaml: string;
  nestedYaml: Readonly<Record<string, string>>;
  pages: readonly DocsNavPage[];
}): DocsNavNode[] {
  const titles = new Map<string, string>();
  const hrefs = new Set<string>();
  for (const page of input.pages) {
    const href = hrefFromDocsSlugs(page.slugs);
    hrefs.add(href);
    titles.set(href, page.title);
  }
  const tree = parseNav(parseYamlNav(input.rootYaml), {
    dir: "",
    nestedYaml: input.nestedYaml,
    hrefs,
    titles,
  }).filter((node) => node.href || (node.children?.length ?? 0) > 0);
  const used = collectHrefs(tree);
  const orphans = [...hrefs]
    .filter((href) => !used.has(href))
    .sort((left, right) => left.localeCompare(right))
    .map((href) => ({ title: titles.get(href) ?? href, href }));
  return orphans.length > 0 ? [...tree, ...orphans] : tree;
}

export function loadDocsNav(locale: string, pages: readonly DocsNavPage[]): DocsNavNode[] {
  const root = path.join(userFacingRoot, "docs", locale);
  let rootYaml = "";
  try {
    rootYaml = readFileSync(path.join(root, ".pages"), "utf8");
  } catch {
    return pages.map((page) => ({ title: page.title, href: hrefFromDocsSlugs(page.slugs) }));
  }
  const nestedYaml: Record<string, string> = {};
  let entries: Dirent[] = [];
  try {
    entries = readdirSync(root, { withFileTypes: true });
  } catch {
    entries = [];
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    try {
      nestedYaml[entry.name] = readFileSync(path.join(root, entry.name, ".pages"), "utf8");
    } catch {
      // Folder has no .pages; infer children from imported slugs.
    }
  }
  return buildDocsNav({ rootYaml, nestedYaml, pages });
}

function parseYamlNav(text: string): unknown[] {
  const loaded: unknown = load(text, { schema: JSON_SCHEMA });
  if (!loaded || typeof loaded !== "object" || Array.isArray(loaded)) return [];
  const nav = (loaded as { nav?: unknown }).nav;
  return Array.isArray(nav) ? nav : [];
}

function parseNav(items: unknown[], ctx: Ctx): DocsNavNode[] {
  const nodes: DocsNavNode[] = [];
  for (const item of items) {
    if (typeof item === "string") {
      if (item === "...") continue;
      if (item.endsWith(".md")) {
        const href = toHref(ctx.dir, item);
        if (ctx.hrefs.has(href)) {
          nodes.push({ title: ctx.titles.get(href) ?? item, href });
        }
        continue;
      }
      const node = directoryNode(item, joinDir(ctx.dir, item), ctx);
      if (node) nodes.push(node);
      continue;
    }
    if (item && typeof item === "object" && !Array.isArray(item)) {
      for (const [label, value] of Object.entries(item as Record<string, unknown>)) {
        const node = resolveEntry(label, value, ctx);
        if (node) nodes.push(node);
      }
    }
  }
  return nodes;
}

function resolveEntry(label: string, value: unknown, ctx: Ctx): DocsNavNode | null {
  if (typeof value === "string") {
    if (value.endsWith(".md")) {
      const href = toHref(ctx.dir, value);
      if (!ctx.hrefs.has(href)) return null;
      return { title: label, href };
    }
    return directoryNode(label, joinDir(ctx.dir, value), ctx);
  }
  if (Array.isArray(value)) {
    return groupNode(label, parseNav(value, ctx));
  }
  return null;
}

function directoryNode(label: string, dir: string, ctx: Ctx): DocsNavNode | null {
  const yaml = ctx.nestedYaml[dir];
  const children = yaml ? parseNav(parseYamlNav(yaml), { ...ctx, dir }) : inferDirectory(dir, ctx);
  return groupNode(label, children, toHref(dir, "index.md"));
}

function inferDirectory(dir: string, ctx: Ctx): DocsNavNode[] {
  const indexHref = toHref(dir, "index.md");
  const prefix = `${indexHref}/`;
  return [...ctx.hrefs]
    .filter((href) => href === indexHref || href.startsWith(prefix))
    .sort((left, right) => {
      if (left === indexHref) return -1;
      if (right === indexHref) return 1;
      return left.localeCompare(right);
    })
    .map((href) => ({
      title: href === indexHref ? "Overview" : (ctx.titles.get(href) ?? href.slice(prefix.length)),
      href,
    }));
}

function groupNode(label: string, children: DocsNavNode[], indexHref?: string): DocsNavNode | null {
  const visible = children.filter((child) => child.href || (child.children?.length ?? 0) > 0);
  if (visible.length === 0) return null;
  const indexChild =
    indexHref === undefined
      ? undefined
      : visible.find((child) => child.href === indexHref && !child.children?.length);
  const rest = indexChild ? visible.filter((child) => child !== indexChild) : visible;
  if (rest.length === 0) {
    const href = indexChild?.href ?? indexHref;
    return href ? { title: label, href } : null;
  }
  if (indexChild?.href) {
    return { title: label, href: indexChild.href, children: rest };
  }
  return { title: label, children: rest };
}

function toHref(dir: string, file: string): string {
  const withoutExt = file.replace(/\.md$/u, "");
  const rel = [dir, withoutExt].filter((part) => part.length > 0).join("/");
  const trimmed = rel.replace(/\/index$/u, "").replace(/^index$/u, "");
  return trimmed.length > 0 ? `/docs/${trimmed}` : "/docs";
}

function joinDir(base: string, child: string): string {
  return base ? `${base}/${child}` : child;
}

function collectHrefs(nodes: readonly DocsNavNode[], into = new Set<string>()): Set<string> {
  for (const node of nodes) {
    if (node.href) into.add(node.href);
    if (node.children) collectHrefs(node.children, into);
  }
  return into;
}
