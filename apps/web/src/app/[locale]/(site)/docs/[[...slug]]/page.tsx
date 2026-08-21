import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { DocsSearch } from "@/components/organisms/docs-search";
import { docsSource } from "@/lib/docs-source";
import { Link } from "@/lib/i18n/navigation";

type Props = { params: Promise<{ locale: string; slug?: string[] }> };

export default async function DocsPage({ params }: Props) {
  const { locale, slug = [] } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("docs");
  const page = docsSource.getPage([locale, ...slug]);
  if (!page) notFound();
  const renderer = await page.data.load();
  const content = await renderer.render();
  const pages = docsSource.getPages().filter((item) => item.slugs[0] === locale);

  return (
    <div className="grid gap-10 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="space-y-5 lg:sticky lg:top-24 lg:self-start">
        <DocsSearch locale={locale} />
        <nav aria-label={t("navAria")} className="space-y-1">
          {pages.map((item) => {
            const relative = item.slugs.slice(1);
            return (
              <Link
                key={item.url}
                href={`/docs/${relative.join("/")}`}
                className="hover:bg-muted block rounded-sm px-3 py-2 text-sm"
              >
                {item.data.title}
              </Link>
            );
          })}
        </nav>
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
