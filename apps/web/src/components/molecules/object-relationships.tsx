import { localizedCountryName } from "@/lib/country-name";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";

export type RelatedService = {
  name: string;
  canonical_domain: string;
  primary_url: string;
  country_codes: string[];
};

export function ObjectRelationships({
  countryCodes,
  services,
  locale,
  labels,
}: {
  countryCodes: readonly string[];
  services: readonly RelatedService[];
  locale: string;
  labels: {
    localization: string;
    linkedServices: string;
    notExclusive: string;
  };
}) {
  const countries = [...new Set(countryCodes)].filter(Boolean);
  if (countries.length === 0 && services.length === 0) return null;

  return (
    <section
      data-ui={UI.component.relationships}
      className="flex flex-wrap items-start gap-x-8 gap-y-3"
      aria-label={labels.linkedServices}
    >
      {countries.length > 0 ? (
        <div className="min-w-0 space-y-1.5">
          <h2 className="text-sm font-medium">{labels.localization}</h2>
          <ul className="flex flex-wrap gap-2">
            {countries.map((code) => (
              <li key={code}>
                <Link
                  href={`/countries/${code}`}
                  className="border-border hover:bg-muted focus-visible:ring-ring inline-flex items-center rounded-md border px-2 py-1 text-sm focus-visible:ring-2 focus-visible:outline-none"
                >
                  {localizedCountryName(code, locale)}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {services.length > 0 ? (
        <div className="min-w-0 space-y-1.5">
          <h2 className="text-sm font-medium">{labels.linkedServices}</h2>
          <p className="text-muted-foreground text-xs">{labels.notExclusive}</p>
          <ul className="flex flex-wrap gap-2">
            {services.map((service) => (
              <li key={service.canonical_domain}>
                <Link
                  href={`/services/${service.canonical_domain}`}
                  className="border-border hover:bg-muted focus-visible:ring-ring inline-flex items-center rounded-md border px-2 py-1 text-sm focus-visible:ring-2 focus-visible:outline-none"
                >
                  {service.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
