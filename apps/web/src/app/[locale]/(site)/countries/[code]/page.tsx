import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { readCountry } from "@/lib/api/catalog";

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
  const display =
    new Intl.DisplayNames([locale], { type: "region" }).of(country.code) ?? country.code;
  return (
    <main className="space-y-8">
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
            <li key={`${item.object_kind}:${item.stable_id}`}>{item.name}</li>
          ))}
        </ul>
      </section>
    </main>
  );
}
