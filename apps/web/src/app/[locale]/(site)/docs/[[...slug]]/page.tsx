import { notFound, redirect } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { DocsNav } from "@/components/organisms/docs-nav";
import { DocsSearch } from "@/components/organisms/docs-search";
import { canonicalDocsSlug, hrefFromDocsSlugs, loadDocsNav } from "@/lib/docs-nav";
import { docsSource } from "@/lib/docs-source";

type Props = { params: Promise<{ locale: string; slug?: string[] }> };

export default async function DocsPage({ params }: Props) {
  const { locale, slug = [] } = await params;
  setRequestLocale(locale);
  const canonical = canonicalDocsSlug(slug);
  if (canonical) {
    redirect(canonical.length > 0 ? `/${locale}/docs/${canonical.join("/")}` : `/${locale}/docs`);
  }
  const t = await getTranslations("docs");
  const page = docsSource.getPage([locale, ...slug]);
  if (!page) notFound();
  const renderer = await page.data.load();
  const content = await renderer.render();
  const pages = docsSource.getPages().filter((item) => item.slugs[0] === locale);
  const tree = loadDocsNav(
    locale,
    pages.map((item) => ({ slugs: item.slugs, title: item.data.title })),
  );
  const currentHref = hrefFromDocsSlugs([locale, ...slug]);

  return (
    <div className="grid gap-10 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="space-y-5 lg:sticky lg:top-24 lg:self-start">
        <DocsSearch locale={locale} />
        <DocsNav tree={tree} currentHref={currentHref} ariaLabel={t("navAria")} />
      </aside>
      <article className="prose-docs max-w-3xl min-w-0">
        <h1>{page.data.title}</h1>
        {page.data.description ? (
          <p className="text-muted-foreground text-lg">{page.data.description}</p>
        ) : null}
        {content.body}
      </article>
    </div>
  );
}

export function generateStaticParams() {
  return docsSource.generateParams().map(({ slug }) => ({ locale: slug[0], slug: slug.slice(1) }));
}
