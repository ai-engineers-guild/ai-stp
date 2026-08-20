import Link from "next/link";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

import { readExternalProduct } from "@/lib/api/catalog";

export default async function ServicePage({
  params,
}: {
  params: Promise<{ locale: string; domain: string }>;
}) {
  const { locale, domain } = await params;
  setRequestLocale(locale);
  if (process.env.NEXT_PUBLIC_EXTERNAL_CATALOG_ENABLED === "false") notFound();
  const service = await readExternalProduct(domain).catch(() => null);
  if (!service) notFound();
  return (
    <main className="space-y-8">
      <header className="space-y-2">
        <p className="text-muted-foreground text-sm">External service</p>
        <h1 className="text-3xl font-medium">{service.name}</h1>
        <a className="underline" href={service.primary_url} rel="noreferrer">
          {service.canonical_domain}
        </a>
      </header>
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
        <h2 className="mb-3 text-xl font-medium">Automations</h2>
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
