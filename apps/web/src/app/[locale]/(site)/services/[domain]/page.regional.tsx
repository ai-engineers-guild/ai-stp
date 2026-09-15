import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { CountryFlag } from "@/components/atoms/country-flag";
import { SeoJsonLd } from "@/components/molecules/seo-json-ld";
import { MarkdownDescription } from "@/components/molecules/markdown-description";
import { readExternalProduct } from "@/lib/api/catalog";
import { localizedCountryName } from "@/lib/country-name";
import { Link } from "@/lib/i18n/navigation";
import { readSeoProfile } from "@/lib/api/seo";
import { metadataFromSeo } from "@/lib/seo/metadata";
import { Icon } from "@/theme";

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
  const objects = service.objects ?? [];
  const components = objects.filter((item) => item.object_kind === "component");
  const setups = objects.filter((item) => item.object_kind === "setup");
  return (
    <main className="space-y-10">
      {seo ? <SeoJsonLd jsonLd={seo.profile.json_ld} /> : null}
      <Button asChild variant="outline" size="sm">
        <Link href="/services">
          <Icon name="arrowLeft" size="sm" />
          {t("backToServices")}
        </Link>
      </Button>
      <header className="max-w-3xl space-y-4">
        <p className="text-muted-foreground text-sm">{t("externalService")}</p>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-4xl font-medium tracking-tight sm:text-5xl">
              {seo?.profile.title ?? service.name}
            </h1>
            <p className="text-muted-foreground mt-2 font-mono text-sm">
              {service.canonical_domain}
            </p>
          </div>
          <a
            className="text-primary inline-flex min-h-11 items-center gap-2 text-sm font-medium underline underline-offset-4"
            href={service.primary_url}
            rel="noreferrer"
          >
            {t("openService")}
            <Icon name="link" size="sm" />
          </a>
        </div>
      </header>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
        <div className="min-w-0 space-y-10">
          {seo?.profile.summary ? (
            <MarkdownDescription source={seo.profile.summary} heading={t("description")} />
          ) : null}
          {seo?.profile.sections
            .filter((section) => section.provenance === "model")
            .map((section) => (
              <MarkdownDescription
                key={section.id}
                source={section.body}
                heading={section.heading}
              />
            ))}
          <ObjectGroups
            components={components}
            setups={setups}
            labels={{
              automations: t("automations"),
              linkedObjectsHint: t("linkedObjectsHint"),
              components: t("components"),
              setups: t("setups"),
            }}
          />
        </div>
        <aside className="border-border bg-card rounded-lg border p-5">
          <h2 className="text-lg font-medium">{t("overview")}</h2>
          <dl className="mt-5 space-y-4 text-sm">
            <div>
              <dt className="text-muted-foreground">{t("countries")}</dt>
              <dd className="mt-2 flex flex-wrap gap-2">
                {service.country_codes.length ? (
                  service.country_codes.map((code) => (
                    <Link
                      className="border-border hover:bg-muted inline-flex items-center gap-2 rounded-md border px-2.5 py-1.5"
                      href={`/countries/${code}`}
                      key={code}
                    >
                      <CountryFlag code={code} compact />
                      {localizedCountryName(code, locale)}
                    </Link>
                  ))
                ) : (
                  <span className="text-muted-foreground">{t("unspecified")}</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{t("linkedObjects")}</dt>
              <dd className="mt-1 font-mono text-sm">{objects.length}</dd>
            </div>
          </dl>
        </aside>
      </div>
    </main>
  );
}

function ObjectGroups({
  components,
  setups,
  labels,
}: {
  components: Array<{ object_kind: "component" | "setup"; stable_id: string; name: string }>;
  setups: Array<{ object_kind: "component" | "setup"; stable_id: string; name: string }>;
  labels: {
    automations: string;
    linkedObjectsHint: string;
    components: string;
    setups: string;
  };
}) {
  if (!components.length && !setups.length) return null;
  return (
    <section aria-labelledby="service-objects-heading" className="space-y-5">
      <div>
        <h2 id="service-objects-heading" className="text-2xl font-medium tracking-tight">
          {labels.automations}
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">{labels.linkedObjectsHint}</p>
      </div>
      <div className="space-y-6">
        {components.length ? <ObjectGroup heading={labels.components} items={components} /> : null}
        {setups.length ? <ObjectGroup heading={labels.setups} items={setups} /> : null}
      </div>
    </section>
  );
}

function ObjectGroup({
  heading,
  items,
}: {
  heading: string;
  items: Array<{ object_kind: "component" | "setup"; stable_id: string; name: string }>;
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">{heading}</h3>
      <ul className="grid gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <li key={`${item.object_kind}:${item.stable_id}`}>
            <Link
              className="border-border bg-card hover:bg-muted focus-visible:ring-ring flex min-h-12 items-center justify-between gap-3 rounded-md border px-4 py-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
              href={`/catalog/${item.object_kind === "component" ? "components" : "setups"}/${item.stable_id}`}
            >
              <span className="min-w-0 break-words">{item.name}</span>
              <Icon name="chevronRight" size="sm" className="text-muted-foreground shrink-0" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
