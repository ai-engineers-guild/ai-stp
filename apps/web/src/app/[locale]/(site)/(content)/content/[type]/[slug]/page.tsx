import type { Metadata } from "next";
import Image from "next/image";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { MarkdownDescription } from "@/components/molecules/markdown-description";
import { SeoJsonLd } from "@/components/molecules/seo-json-ld";
import { readPublishedContent } from "@/lib/api/content";
import { readSeoProfile } from "@/lib/api/seo";
import { metadataFromSeo } from "@/lib/seo/metadata";
import { publicOrigin } from "@/lib/site";
import { Link } from "@/lib/i18n/navigation";

type Props = { params: Promise<{ locale: string; type: string; slug: string }> };

export const dynamic = "force-dynamic";
export const dynamicParams = true;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale, type, slug } = await params;
  const entry = await readPublishedContent(locale, type, slug);
  if (!entry) return {};
  const path = `/${locale}/content/${type}/${slug}`;
  const seo = await readSeoProfile("article", `${type}:${slug}`, locale);
  const metadata = metadataFromSeo(seo, {
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
  });
  if (!entry.cover_image) return metadata;
  const image = new URL(entry.cover_image, publicOrigin()).toString();
  return {
    ...metadata,
    openGraph: {
      ...(metadata.openGraph ?? {}),
      images: [{ url: image, width: 1200, height: 630, alt: entry.cover_alt ?? entry.title }],
    },
    twitter: {
      ...(metadata.twitter ?? {}),
      card: "summary_large_image",
      images: [{ url: image, alt: entry.cover_alt ?? entry.title }],
    },
  };
}

export default async function ContentDetail({ params }: Props) {
  const { locale, type, slug } = await params;
  setRequestLocale(locale);
  const entry = await readPublishedContent(locale, type, slug);
  if (!entry) notFound();
  const t = await getTranslations("content");
  const canonical = new URL(`/${locale}/content/${type}/${slug}`, publicOrigin()).toString();
  const seo = await readSeoProfile("article", `${type}:${slug}`, locale);
  const jsonLd = seo?.profile.json_ld ?? {
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
      <SeoJsonLd jsonLd={jsonLd} />
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
          aria-label={t("tagsLabel")}
        >
          {entry.tags.map((tag) => (
            <li key={tag} className="bg-muted rounded-md px-2.5 py-1 font-mono text-xs">
              {tag}
            </li>
          ))}
        </ul>
      </header>
      {entry.cover_image ? (
        <Image
          src={entry.cover_image}
          alt={entry.cover_alt ?? entry.title}
          width={1200}
          height={630}
          priority
          className="mx-auto h-auto max-h-[42rem] w-full max-w-4xl rounded-xl object-cover"
        />
      ) : null}
      <div className="mx-auto w-full max-w-4xl">
        <MarkdownDescription
          source={entry.body}
          heading={t("bodyHeading")}
          article
          articleTitle={entry.title}
          articleCoverImage={entry.cover_image}
        />
      </div>
    </article>
  );
}
