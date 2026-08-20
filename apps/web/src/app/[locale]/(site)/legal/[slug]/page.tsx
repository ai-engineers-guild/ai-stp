import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Link } from "@/lib/i18n/navigation";

const POLICY_SLUGS = ["privacy", "cookies", "service-rules", "licensing"] as const;
type PolicySlug = (typeof POLICY_SLUGS)[number];

type PageProps = {
  params: Promise<{ locale: string; slug: string }>;
};

function isPolicySlug(value: string): value is PolicySlug {
  return (POLICY_SLUGS as readonly string[]).includes(value);
}

/** Legal policy template (SPEC-031). Published revisions from API land later. */
export default async function LegalPolicyPage({ params }: PageProps) {
  const { locale, slug } = await params;
  setRequestLocale(locale);
  if (!isPolicySlug(slug)) {
    notFound();
  }
  const t = await getTranslations("legal");

  return (
    <article className="grid gap-12 py-6 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-20 lg:py-12">
      <aside className="space-y-5 lg:sticky lg:top-28 lg:self-start">
        <Link
          href="/"
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-flex min-h-11 items-center font-mono text-xs uppercase underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:outline-none"
        >
          ← {t("backHome")}
        </Link>
        <nav aria-label={t("policies")} className="border-t pt-5">
          <p className="text-muted-foreground mb-3 font-mono text-xs uppercase">{t("policies")}</p>
          <ul className="space-y-1">
            {POLICY_SLUGS.map((item) => (
              <li key={item}>
                <Link
                  href={`/legal/${item}`}
                  aria-current={item === slug ? "page" : undefined}
                  className={`focus-visible:ring-ring block rounded-sm px-2 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none ${
                    item === slug
                      ? "bg-muted text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {t(`${item}.title`)}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <div className="max-w-3xl space-y-10">
        <header className="space-y-6 border-b pb-8">
          <h1 className="text-4xl font-medium tracking-[-0.04em] text-balance sm:text-6xl">
            {t(`${slug}.title`)}
          </h1>
          <p className="text-muted-foreground max-w-2xl text-sm leading-relaxed">
            {t("revisionNote")}
          </p>
          <dl className="grid gap-4 font-mono text-xs sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground mb-1 uppercase">{t("version")}</dt>
              <dd>1.0</dd>
            </div>
            <div>
              <dt className="text-muted-foreground mb-1 uppercase">{t("effective")}</dt>
              <dd>
                <time dateTime="2026-08-05">2026-08-05</time>
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground mb-1 uppercase">{t("language")}</dt>
              <dd className="uppercase">{locale}</dd>
            </div>
          </dl>
        </header>
        <section className="space-y-4" aria-labelledby="policy-text">
          <h2 id="policy-text" className="font-mono text-xs font-medium uppercase">
            {t("contents")}
          </h2>
          <p className="max-w-[70ch] text-base leading-8">{t(`${slug}.body`)}</p>
        </section>
      </div>
    </article>
  );
}
