export function hrefFromDocsSlugs(slugs: readonly string[]): string {
  const relative = slugs.slice(1).filter((part) => part.length > 0);
  return relative.length > 0 ? `/docs/${relative.join("/")}` : "/docs";
}

/** Relative Markdown links keep the `.md` suffix; map them onto the docs slug. */
export function canonicalDocsSlug(slug: readonly string[]): string[] | null {
  if (slug.length === 0) return null;
  const last = slug[slug.length - 1] ?? "";
  if (!last.endsWith(".md")) return null;
  const next = [...slug.slice(0, -1), last.replace(/\.md$/u, "")];
  if (next.at(-1) === "index") next.pop();
  return next;
}

/** Browser Markdown hrefs such as `/en/docs/cli/index.md` onto the docs route. */
export function docsMarkdownRedirectPath(pathname: string): string | null {
  const match = pathname.match(/^\/(en|ru)(\/ai)?\/docs\/(.+)\.md\/?$/u);
  if (!match) return null;
  const locale = match[1] ?? "en";
  const machine = match[2] ?? "";
  const rest = (match[3] ?? "").replace(/\/index$/u, "");
  return rest.length > 0 ? `/${locale}${machine}/docs/${rest}` : `/${locale}${machine}/docs`;
}
