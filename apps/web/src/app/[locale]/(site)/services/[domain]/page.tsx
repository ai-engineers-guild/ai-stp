import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { SeoJsonLd } from "@/components/molecules/seo-json-ld";
import { MarkdownDescription } from "@/components/molecules/markdown-description";
import { readExternalProduct } from "@/lib/api/catalog";
import { readSeoProfile } from "@/lib/api/seo";
import { metadataFromSeo } from "@/lib/seo/metadata";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; domain: string }>;
}): Promise<Metadata> {
  const { locale, domain } = await params;
  const seo = await readSeoProfile("service", domain, locale);
  return metadataFromSeo(seo, { title: domain });
}

export default async function ServicePage({
  params,
}: {
  params: Promise<{ locale: string; domain: string }>;
}) {
  const { locale, domain } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("regionalServices");
  if (process.env.NEXT_PUBLIC_EXTERNAL_CATALOG_ENABLED === "false") notFound();
  const service = await readExternalProduct(domain).catch(() => null);
  if (!service) notFound();
  const seo = await readSeoProfile("service", domain, locale);
  return (
    <main className="space-y-8">
      {seo ? <SeoJsonLd jsonLd={seo.profile.json_ld} /> : null}
      <header className="space-y-2">
        <p className="text-muted-foreground text-sm">{t("externalService")}</p>
        <h1 className="text-3xl font-medium">{service.name}</h1>
        <a className="underline" href={service.primary_url} rel="noreferrer">
          {service.canonical_domain}
        </a>
      </header>
      {seo ? (
        <MarkdownDescription source={seo.profile.summary} heading={seo.profile.title} />
      ) : null}
      {seo?.profile.sections
        .filter((section) => section.provenance === "model")
        .map((section) => (
          <MarkdownDescription key={section.id} source={section.body} heading={section.heading} />
        ))}
      <div className="flex gap-2">
        {service.country_codes.map((code) => (
          <Link
            className="rounded-full border px-3 py-1"
            href={`/${locale}/countries/${code}`}
            key={code}
          >
            {code}
          </Link>
        ))}
      </div>
      <section>
        <h2 className="mb-3 text-xl font-medium">{t("automations")}</h2>
        <ul className="space-y-2">
          {service.objects?.map((item) => (
            <li key={`${item.object_kind}:${item.stable_id}`}>
              <Link
                className="underline"
                href={`/${locale}/catalog/${item.object_kind}s/${item.stable_id}`}
              >
                {item.name}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
