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
        <article className="grid gap-5 border-b pb-10 lg:grid-cols-[8rem_minmax(0,1fr)_18rem] lg:items-center lg:gap-8">
          <div className="order-1 space-y-2 font-mono text-xs lg:row-start-1 lg:self-start">
            <p className="text-primary uppercase">{t("featured")}</p>
            <p>{t(featured.type)}</p>
            <time className="text-muted-foreground block" dateTime={featured.published_at}>
              {featured.published_at}
            </time>
          </div>
          {featured.cover_image ? (
            <Image
              src={featured.cover_image}
              alt={featured.cover_alt ?? featured.title}
              width={640}
              height={360}
              className="order-2 h-36 w-full rounded-lg object-cover sm:h-44 lg:col-start-3 lg:row-start-1 lg:h-36"
            />
          ) : null}
          <div
            className={`order-3 max-w-2xl space-y-3 lg:row-start-1 ${
              featured.cover_image ? "lg:col-start-2" : "lg:col-span-2 lg:col-start-2"
            }`}
          >
            <h2 className="text-2xl font-medium tracking-[-0.025em] text-balance sm:text-4xl">
              <Link
                className="decoration-primary underline-offset-8 hover:underline"
                href={`/content/${featured.type}/${featured.slug}`}
              >
                {featured.title}
              </Link>
            </h2>
            <p className="text-muted-foreground leading-relaxed">{featured.description}</p>
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
              className="group grid gap-x-6 gap-y-4 py-6 md:grid-cols-[8rem_minmax(0,1fr)_12rem_auto] md:items-center"
            >
              <div className="text-muted-foreground order-1 space-y-1 font-mono text-xs md:row-start-1">
                <p>{t(entry.type)}</p>
                <time dateTime={entry.published_at}>{entry.published_at}</time>
              </div>
              {entry.cover_image ? (
                <Image
                  src={entry.cover_image}
                  alt={entry.cover_alt ?? entry.title}
                  width={640}
                  height={360}
                  className="order-2 h-28 w-full rounded-lg object-cover md:col-start-3 md:row-start-1 md:h-20"
                />
              ) : null}
              <div
                className={`order-3 max-w-2xl space-y-1 md:row-start-1 ${
                  entry.cover_image ? "md:col-start-2" : "md:col-span-2 md:col-start-2"
                }`}
              >
                <h3 className="text-xl font-medium tracking-[-0.02em] text-balance sm:text-2xl">
                  <Link
                    className="decoration-primary underline-offset-6 group-hover:underline"
                    href={`/content/${entry.type}/${entry.slug}`}
                  >
                    {entry.title}
                  </Link>
                </h3>
                <p className="text-muted-foreground text-sm leading-relaxed">{entry.description}</p>
              </div>
              <span
                className="text-muted-foreground order-4 hidden text-xl transition-transform group-hover:translate-x-1 md:col-start-4 md:row-start-1 md:block"
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
