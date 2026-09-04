import type { Metadata } from "next";
import Image from "next/image";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { listPublishedContent } from "@/lib/api/content";
import { CONTENT_TYPES } from "@/lib/content/source";
import { Link } from "@/lib/i18n/navigation";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "content" });
  return { title: t("title"), description: t("description") };
}

export default async function ContentIndex({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("content");
  const entries = await listPublishedContent(locale);
  const [featured, ...latest] = entries;
  return (
    <section className="space-y-16 py-6 sm:py-12">
      <header className="grid gap-8 border-b pb-10 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-end">
        <div className="max-w-3xl space-y-5">
          <h1 className="text-5xl font-medium tracking-[-0.04em] text-balance sm:text-7xl">
            {t("title")}
          </h1>
          <p className="text-muted-foreground max-w-2xl text-lg leading-relaxed sm:text-xl">
            {t("description")}
          </p>
        </div>
        <div className="space-y-3 font-mono text-xs">
          <p className="text-muted-foreground uppercase">{t("allTypes")}</p>
          <ul className="flex flex-wrap gap-x-4 gap-y-2 lg:grid lg:grid-cols-2">
            {CONTENT_TYPES.map((type) => (
              <li key={type}>{t(type)}</li>
            ))}
          </ul>
        </div>
      </header>

      {featured ? (
        <article className="grid gap-8 border-b pb-14 lg:grid-cols-[minmax(0,0.65fr)_minmax(0,1.35fr)] lg:gap-16">
          <div className="space-y-3 font-mono text-xs">
            <p className="text-primary uppercase">{t("featured")}</p>
            <p>{t(featured.type)}</p>
            <time className="text-muted-foreground block" dateTime={featured.published_at}>
              {featured.published_at}
            </time>
          </div>
          <div className="max-w-3xl space-y-5">
            {featured.cover_image ? (
              <Image
                src={featured.cover_image}
                alt={featured.cover_alt ?? featured.title}
                width={1200}
                height={630}
                className="h-auto max-h-[32rem] w-full rounded-xl object-cover"
              />
            ) : null}
            <h2 className="text-3xl font-medium tracking-[-0.03em] text-balance sm:text-5xl">
              <Link
                className="decoration-primary underline-offset-8 hover:underline"
                href={`/content/${featured.type}/${featured.slug}`}
              >
                {featured.title}
              </Link>
            </h2>
            <p className="text-muted-foreground max-w-2xl text-lg leading-relaxed">
              {featured.description}
            </p>
            <Link
              href={`/content/${featured.type}/${featured.slug}`}
              className="focus-visible:ring-ring inline-flex min-h-11 items-center font-mono text-xs font-medium uppercase underline decoration-1 underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
            >
              {t("read")} →
            </Link>
          </div>
        </article>
      ) : null}

      <section className="space-y-4" aria-labelledby="latest-content">
        <h2 id="latest-content" className="font-mono text-xs font-medium uppercase">
          {t("latest")}
        </h2>
        <div className="divide-border divide-y border-y">
          {latest.map((entry) => (
            <article
              key={`${entry.type}:${entry.slug}`}
              className="group grid gap-4 py-7 md:grid-cols-[10rem_minmax(0,1fr)_auto] md:items-start"
            >
              <div className="text-muted-foreground space-y-1 font-mono text-xs">
                <p>{t(entry.type)}</p>
                <time dateTime={entry.published_at}>{entry.published_at}</time>
              </div>
              <div className="max-w-2xl space-y-2">
                {entry.cover_image ? (
                  <Image
                    src={entry.cover_image}
                    alt={entry.cover_alt ?? entry.title}
                    width={640}
                    height={360}
                    className="mb-4 h-32 w-full rounded-lg object-cover"
                  />
                ) : null}
                <h3 className="text-2xl font-medium tracking-[-0.02em] text-balance">
                  <Link
                    className="decoration-primary underline-offset-6 group-hover:underline"
                    href={`/content/${entry.type}/${entry.slug}`}
                  >
                    {entry.title}
                  </Link>
                </h3>
                <p className="text-muted-foreground leading-relaxed">{entry.description}</p>
              </div>
              <span
                className="text-muted-foreground hidden text-xl transition-transform group-hover:translate-x-1 md:block"
                aria-hidden
              >
                →
              </span>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}
