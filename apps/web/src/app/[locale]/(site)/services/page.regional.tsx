import { getTranslations, setRequestLocale } from "next-intl/server";

import {
  RegionalServicesExplorer,
  type RegionalServiceLabels,
} from "@/components/organisms/regional-services-explorer";
import { listExternalProducts } from "@/lib/api/catalog";

/* Regional services surface (established ai_stp world).
 * THESIS: a CIS market atlas that leads into real, filterable services, not a tall filter form under a heading.
 * OWN-WORLD: sand/ink surfaces, 1px borders, signal orange, Plex, geometric flags, authored dusk survey plate.
 * STORY: visitor sees the region, picks a market or service, opens details or the catalog with filters applied.
 * FIRST VIEWPORT: dark atlas plate; title left; CIS flags in a slow orbit; compact filters below; no fake counts.
 * FORM: atlas-constellation inside the product system; code-led. FINISH: inspect, tests, surface brief. */

export default async function RegionalServicesPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("regionalServices");
  const services = await listExternalProducts()
    .then((result) => result.items)
    .catch(() => []);
  const labels: RegionalServiceLabels = {
    title: t("title"),
    subtitle: t("subtitle"),
    heroArtAlt: t("heroArtAlt"),
    cisRegion: t("cisRegion"),
    countries: t("countries"),
    services: t("services"),
    allCountries: t("allCountries"),
    allServices: t("allServices"),
    available: t("available"),
    result: t("result"),
    results: t("results"),
    details: t("details"),
    automations: t("automations"),
    empty: t("empty"),
    unspecified: t("unspecified"),
    openCatalog: t("openCatalog"),
  };
  return <RegionalServicesExplorer services={services} locale={locale} labels={labels} />;
}
