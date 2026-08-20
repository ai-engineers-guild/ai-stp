import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { MarkdownDescription } from "@/components/molecules/markdown-description";
import { allContentEntries, findContent } from "@/lib/content/source";
import { publicOrigin } from "@/lib/site";
import { Link } from "@/lib/i18n/navigation";

type Props = { params: Promise<{ locale: string; type: string; slug: string }> };

export function generateStaticParams() {
  return allContentEntries()
    .filter((entry) => !entry.draft)
    .map(({ locale, type, slug }) => ({ locale, type, slug }));
}

export const dynamicParams = false;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale, type, slug } = await params;
  const entry = findContent(locale, type, slug);
  if (!entry) return {};
  const path = `/${locale}/content/${type}/${slug}`;
  return {
    title: entry.title,
    description: entry.description,
    alternates: {
      canonical: path,
      languages: {
        en: `/en/content/${type}/${slug}`,
        ru: `/ru/content/${type}/${slug}`,
      },
    },
    openGraph: { type: "article", title: entry.title, description: entry.description, url: path },
  };
}

export default async function ContentDetail({ params }: Props) {
  const { locale, type, slug } = await params;
  setRequestLocale(locale);
  const entry = findContent(locale, type, slug);
  if (!entry) notFound();
  const t = await getTranslations("content");
  const canonical = new URL(`/${locale}/content/${type}/${slug}`, publicOrigin()).toString();
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": type === "blog_post" ? "BlogPosting" : type === "article" ? "TechArticle" : "Article",
    headline: entry.title,
    description: entry.description,
    datePublished: entry.published_at,
    inLanguage: locale,
    mainEntityOfPage: canonical,
  };
  return (
    <article className="mx-auto max-w-5xl space-y-12 py-6 sm:py-12">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replaceAll("<", "\\u003c") }}
      />
      <header className="grid gap-7 border-b pb-10 lg:grid-cols-[minmax(0,1fr)_12rem] lg:items-end">
        <Link
          href="/content"
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-flex min-h-11 items-center font-mono text-xs uppercase underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:outline-none"
        >
          ← {t("title")}
        </Link>
        <div className="flex flex-wrap gap-3 font-mono text-xs lg:col-start-1">
          <span className="text-primary uppercase">{t(entry.type)}</span>
          <span className="text-muted-foreground" aria-hidden>
            ·
          </span>
          <time dateTime={entry.published_at}>{entry.published_at}</time>
        </div>
        <h1 className="max-w-4xl text-4xl font-medium tracking-[-0.035em] text-balance sm:text-6xl lg:col-span-2 lg:text-7xl">
          {entry.title}
        </h1>
        <p className="text-muted-foreground max-w-2xl text-lg leading-relaxed sm:text-xl lg:col-start-1">
          {entry.description}
        </p>
        <ul
          className="flex flex-wrap gap-2 lg:col-start-2 lg:row-start-4 lg:justify-end"
          aria-label="Tags"
        >
          {entry.tags.map((tag) => (
            <li key={tag} className="bg-muted rounded-md px-2.5 py-1 font-mono text-xs">
              {tag}
            </li>
          ))}
        </ul>
      </header>
      <div className="mx-auto w-full max-w-4xl">
        <MarkdownDescription source={entry.body} heading={t("bodyHeading")} article />
      </div>
    </article>
  );
}
