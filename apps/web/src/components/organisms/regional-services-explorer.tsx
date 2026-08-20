"use client";

import { useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";

import { Button } from "@/components/atoms/button";
import {
  CountryFlag,
  isCisCountryCode,
  type CisCountryCode,
} from "@/components/atoms/country-flag";
import type { ExternalProduct } from "@/lib/api/catalog";
import { CATALOG_UNSPECIFIED_FILTER } from "@/lib/catalog-query";
import { cn } from "@/lib/cn";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme";

export type RegionalServiceLabels = {
  title: string;
  subtitle: string;
  heroArtAlt: string;
  cisRegion: string;
  countries: string;
  services: string;
  allCountries: string;
  allServices: string;
  available: string;
  result: string;
  results: string;
  details: string;
  automations: string;
  empty: string;
  unspecified: string;
  openCatalog: string;
};

/** West-to-east ring so the constellation reads as a region, not an alphabet. */
const CIS_RING = [
  "MD",
  "BY",
  "RU",
  "KZ",
  "KG",
  "TJ",
  "UZ",
  "AZ",
  "AM",
] as const satisfies readonly CisCountryCode[];

const CIS_NODES = CIS_RING.map((code, index) => {
  const angle = ((-90 + index * (360 / CIS_RING.length)) * Math.PI) / 180;
  return {
    code,
    x: `${(50 + 40 * Math.cos(angle)).toFixed(2)}%`,
    y: `${(50 + 36 * Math.sin(angle)).toFixed(2)}%`,
  };
});

export function RegionalServicesExplorer({
  services,
  locale,
  labels,
}: {
  services: ExternalProduct[];
  locale: string;
  labels: RegionalServiceLabels;
}) {
  const names = useMemo(() => new Intl.DisplayNames([locale], { type: "region" }), [locale]);
  const countries = useMemo(() => {
    const codes = [...new Set(services.flatMap((item) => item.country_codes))].sort();
    return services.some((item) => item.country_codes.length === 0)
      ? [CATALOG_UNSPECIFIED_FILTER, ...codes]
      : codes;
  }, [services]);
  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [selectedServices, setSelectedServices] = useState<string[]>([]);
  const availableServices = selectedCountries.length
    ? services.filter((service) => matchesCountrySelection(service, selectedCountries))
    : services;
  const selectedInView = selectedServices.filter((domain) =>
    availableServices.some((service) => service.canonical_domain === domain),
  );
  const visible = selectedInView.length
    ? availableServices.filter((service) => selectedInView.includes(service.canonical_domain))
    : availableServices;
  const catalogHref = catalogResultsHref(selectedCountries, selectedInView);
  const extraCountryFilters = countries.filter((code) => !isCisCountryCode(code));

  function toggle(value: string, set: Dispatch<SetStateAction<string[]>>) {
    set((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
    );
  }

  return (
    <div data-ui={UI.services.page} className="space-y-8">
      <Hero
        labels={labels}
        countries={countries}
        selectedCountries={selectedCountries}
        names={names}
        onToggle={(code) => {
          toggle(code, setSelectedCountries);
        }}
      />

      <section
        data-ui={UI.services.filters}
        className="border-border bg-card rounded-lg border p-3 sm:p-4"
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <fieldset>
            <legend className="mb-2 text-xs font-medium">{labels.countries}</legend>
            <div className="flex flex-wrap gap-1.5">
              <FilterChip
                pressed={!selectedCountries.length}
                onClick={() => {
                  setSelectedCountries([]);
                }}
              >
                {labels.allCountries}
              </FilterChip>
              {extraCountryFilters.map((code) => (
                <FilterChip
                  key={code}
                  pressed={selectedCountries.includes(code)}
                  ariaLabel={
                    code === CATALOG_UNSPECIFIED_FILTER
                      ? labels.unspecified
                      : (names.of(code) ?? code)
                  }
                  onClick={() => {
                    toggle(code, setSelectedCountries);
                  }}
                >
                  <CountryFlag code={code} compact />
                  <span>
                    {code === CATALOG_UNSPECIFIED_FILTER
                      ? labels.unspecified
                      : (names.of(code) ?? code)}
                  </span>
                </FilterChip>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="mb-2 text-xs font-medium">{labels.services}</legend>
            <div className="flex flex-wrap gap-1.5">
              <FilterChip
                pressed={!selectedServices.length}
                onClick={() => {
                  setSelectedServices([]);
                }}
              >
                {labels.allServices}
              </FilterChip>
              {availableServices.map((service) => (
                <FilterChip
                  key={service.canonical_domain}
                  pressed={selectedServices.includes(service.canonical_domain)}
                  title={service.canonical_domain}
                  onClick={() => {
                    toggle(service.canonical_domain, setSelectedServices);
                  }}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{service.name}</span>
                    <span className="text-muted-foreground block truncate font-mono text-[10px]">
                      {service.canonical_domain}
                    </span>
                  </span>
                </FilterChip>
              ))}
            </div>
          </fieldset>
        </div>
      </section>

      <section data-ui={UI.services.results} aria-labelledby="service-grid-title">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 id="service-grid-title" className="text-2xl font-medium">
              {labels.available}
            </h2>
            <p className="text-muted-foreground mt-1 text-sm">
              {visible.length} {visible.length === 1 ? labels.result : labels.results}
            </p>
          </div>
          <Button asChild>
            <Link href={catalogHref} prefetch={false}>
              <Icon name="filter" size="sm" />
              {labels.openCatalog}
            </Link>
          </Button>
        </div>
        {visible.length ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {visible.map((service) => (
              <ServiceTile
                key={service.canonical_domain}
                service={service}
                labels={labels}
                names={names}
              />
            ))}
          </div>
        ) : (
          <div className="border-border text-muted-foreground rounded-lg border border-dashed p-10 text-center text-sm">
            {labels.empty}
          </div>
        )}
      </section>
    </div>
  );
}

function Hero({
  labels,
  countries,
  selectedCountries,
  names,
  onToggle,
}: {
  labels: RegionalServiceLabels;
  countries: string[];
  selectedCountries: string[];
  names: Intl.DisplayNames;
  onToggle: (code: string) => void;
}) {
  return (
    <section
      data-ui={UI.services.hero}
      className="dark border-border relative overflow-hidden rounded-xl border"
    >
      <div className="bg-primary absolute inset-x-0 top-0 z-20 h-0.5" aria-hidden="true" />
      <picture>
        <source srcSet="/brand/regional-services-atlas.webp" type="image/webp" />
        <img
          src="/brand/regional-services-atlas.jpg"
          alt={labels.heroArtAlt}
          width={1280}
          height={720}
          fetchPriority="high"
          decoding="async"
          className="absolute inset-0 h-full w-full object-cover"
        />
      </picture>
      <div
        className="from-background via-background/80 to-background/20 absolute inset-0 bg-gradient-to-r"
        aria-hidden="true"
      />
      <div
        className="from-background/70 absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t to-transparent"
        aria-hidden="true"
      />
      <div className="relative z-10 grid items-center gap-8 px-5 py-8 sm:px-8 sm:py-10 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,22rem)] lg:gap-10">
        <header className="max-w-xl space-y-4">
          <h1 className="text-4xl font-medium tracking-tight text-white sm:text-5xl">
            {labels.title}
          </h1>
          <p className="max-w-prose text-base leading-relaxed text-white/70 sm:text-lg">
            {labels.subtitle}
          </p>
        </header>
        <div className="cis-constellation" role="group" aria-label={labels.cisRegion}>
          <div className="cis-constellation__orbit" aria-hidden="true" />
          <div
            className="cis-constellation__orbit cis-constellation__orbit--inner"
            aria-hidden="true"
          />
          <div className="cis-constellation__hub" aria-hidden="true">
            <img
              src="/brand/logo-mark.png"
              alt=""
              width={36}
              height={36}
              className="h-9 w-9 opacity-80"
            />
          </div>
          <div className="cis-constellation__ring">
            {CIS_NODES.map((node) => {
              const selectable = countries.includes(node.code);
              const selected = selectedCountries.includes(node.code);
              const name = names.of(node.code) ?? node.code;
              const mark = (
                <>
                  <CountryFlag
                    code={node.code}
                    className="h-9 w-[3.35rem] shadow-md sm:h-10 sm:w-16"
                  />
                  <span
                    aria-hidden="true"
                    className="text-muted-foreground mt-1 block text-center font-mono text-[10px] tracking-wide"
                  >
                    {node.code}
                  </span>
                </>
              );
              return (
                <div
                  key={node.code}
                  className="cis-constellation__node"
                  style={{ ["--x" as string]: node.x, ["--y" as string]: node.y }}
                  data-cis-flag={node.code}
                >
                  {selectable ? (
                    <button
                      type="button"
                      aria-pressed={selected}
                      aria-label={name}
                      onClick={() => {
                        onToggle(node.code);
                      }}
                      className={cn(
                        "focus-visible:ring-ring rounded-sm border text-left focus-visible:ring-2 focus-visible:outline-none",
                        selected ? "border-primary" : "border-transparent",
                      )}
                    >
                      {mark}
                    </button>
                  ) : (
                    <div aria-hidden="true">{mark}</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

function FilterChip({
  pressed,
  onClick,
  children,
  ariaLabel,
  title,
}: {
  pressed: boolean;
  onClick: () => void;
  children: ReactNode;
  ariaLabel?: string;
  title?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      aria-label={ariaLabel}
      title={title}
      onClick={onClick}
      className={cn(
        "focus-visible:ring-ring inline-flex min-h-9 max-w-full items-center gap-2 rounded-sm border px-2.5 py-1.5 text-left text-sm focus-visible:ring-2 focus-visible:outline-none",
        pressed ? "border-primary bg-primary/15 ring-ring ring-1" : "border-border hover:bg-muted",
      )}
    >
      {children}
    </button>
  );
}

function ServiceTile({
  service,
  labels,
  names,
}: {
  service: ExternalProduct;
  labels: RegionalServiceLabels;
  names: Intl.DisplayNames;
}) {
  const codes = service.country_codes;
  return (
    <article className="border-border bg-card flex min-h-44 flex-col rounded-lg border p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-lg font-medium">{service.name}</h3>
          <p className="text-muted-foreground font-mono text-xs">{service.canonical_domain}</p>
        </div>
        <Icon name="link" size="sm" className="text-primary mt-1 shrink-0" />
      </div>
      <div className="text-muted-foreground mb-5 flex flex-wrap items-center gap-2 text-xs">
        {codes.length ? (
          codes.map((code) => <CountryFlag key={code} code={code} compact />)
        ) : (
          <CountryFlag code={CATALOG_UNSPECIFIED_FILTER} compact />
        )}
        <span>
          {codes.length
            ? codes.map((code) => names.of(code) ?? code).join(", ")
            : labels.unspecified}
        </span>
      </div>
      <div className="mt-auto flex flex-wrap gap-3 text-sm">
        <Link
          href={`/services/${service.canonical_domain}`}
          className="font-medium underline underline-offset-4"
        >
          {labels.details}
        </Link>
        <Link
          href={catalogResultsHref([], [service.canonical_domain])}
          prefetch={false}
          className="text-muted-foreground underline underline-offset-4"
        >
          {labels.automations}
        </Link>
      </div>
    </article>
  );
}

function matchesCountrySelection(service: ExternalProduct, selectedCountries: string[]): boolean {
  if (
    selectedCountries.includes(CATALOG_UNSPECIFIED_FILTER) &&
    service.country_codes.length === 0
  ) {
    return true;
  }
  return service.country_codes.some((code) => selectedCountries.includes(code));
}

function catalogResultsHref(countries: string[], domains: string[]): string {
  const params = new URLSearchParams({
    include_experimental: "1",
    resource: "all",
    page_size: "25",
    page: "1",
    view: "list",
  });
  if (domains.length) params.set("service_domains", domains.join(","));
  if (countries.length) params.set("country_codes", countries.join(","));
  return `/catalog?${params.toString()}`;
}
