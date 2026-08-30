import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { SeoJsonLd } from "@/components/molecules/seo-json-ld";
import { readCountry } from "@/lib/api/catalog";
import { readSeoProfile } from "@/lib/api/seo";
import { metadataFromSeo } from "@/lib/seo/metadata";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; code: string }>;
}): Promise<Metadata> {
  const { locale, code } = await params;
  const seo = await readSeoProfile("country", code.toUpperCase(), locale);
  return metadataFromSeo(seo, { title: code.toUpperCase() });
}

export default async function CountryPage({
  params,
}: {
  params: Promise<{ locale: string; code: string }>;
}) {
  const { locale, code } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("regionalServices");
  if (process.env.NEXT_PUBLIC_EXTERNAL_CATALOG_ENABLED === "false") notFound();
  const country = await readCountry(code).catch(() => null);
  if (!country) notFound();
  const seo = await readSeoProfile("country", country.code, locale);
  const display =
    new Intl.DisplayNames([locale], { type: "region" }).of(country.code) ?? country.code;
  return (
    <main className="space-y-8">
      {seo ? <SeoJsonLd jsonLd={seo.profile.json_ld} /> : null}
      <header>
        <p className="text-muted-foreground text-sm">{country.code}</p>
        <h1 className="text-3xl font-medium">{display}</h1>
      </header>
      <section>
        <h2 className="mb-3 text-xl font-medium">{t("services")}</h2>
        <ul className="space-y-2">
          {country.services.map((item) => (
            <li key={item.canonical_domain}>
              <Link className="underline" href={`/${locale}/services/${item.canonical_domain}`}>
                {item.name}
              </Link>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2 className="mb-3 text-xl font-medium">{t("automations")}</h2>
        <ul className="space-y-2">
          {country.objects.map((item) => (
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
