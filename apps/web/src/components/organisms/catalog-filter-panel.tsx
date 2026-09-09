/* eslint-disable max-lines -- Filter panel keeps the related facets in one render owner. */
"use client";

import { useMemo, useState } from "react";

import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import type { CatalogAuthorOption, ExternalProduct } from "@/lib/api/catalog";
import { CATALOG_UNSPECIFIED_FILTER, type ParsedCatalogQuery } from "@/lib/catalog-query";
import { localizedCountryName } from "@/lib/country-name";
import { COMPONENT_TYPE_FACETS, HARNESS_FACETS, TAG_FACETS } from "@/lib/tag-vocabulary";

const selectClassName =
  "h-11 w-full rounded-sm border border-input bg-background px-3 text-base text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:text-sm";

export type CatalogFilterPanelLabels = {
  experimentalConsent: string;
  tagFilter: string;
  harnessFilter: string;
  typeFilter: string;
  supportTierFilter: string;
  supportStateFilter: string;
  anyOption: string;
  applyFilters: string;
  filtersButton: string;
  filterHelpTitle: string;
  filterHelpBody: string;
  closeFilters: string;
  resetAll: string;
  resourceLegend: string;
  components: string;
  setups: string;
  filterHelpLabel: string;
  tagFilterHelp?: string;
  harnessFilterHelp?: string;
  typeFilterHelp?: string;
  authorFilterHelp?: string;
  verifiedOnlyHelp?: string;
  verificationHelp?: string;
  safetyPercentHelp?: string;
  countryFilterHelp?: string;
  serviceFilterHelp?: string;
  updatedRangeHelp?: string;
  searchOptions: string;
  authorFilter: string;
  authorSearch?: string;
  authorSelectionSuffix?: string;
  authorSelectionHint?: string;
  verifiedOnly: string;
  verificationFilter?: string;
  verifiedOption?: string;
  notVerifiedOption?: string;
  safetyPercentFilter?: string;
  serviceFilter: string;
  countryFilter: string;
  unspecifiedOption?: string;
  updatedFrom?: string;
  updatedTo?: string;
  clearUpdatedRange?: string;
};
// eslint-disable-next-line max-lines-per-function, complexity
export function CatalogFilterPanel({
  query,
  labels,
  services,
  authors = [],
  locale = "en",
  hideAuthorFilter = false,
}: {
  query: ParsedCatalogQuery;
  labels: CatalogFilterPanelLabels;
  services: ExternalProduct[];
  authors?: CatalogAuthorOption[];
  locale?: string;
  hideAuthorFilter?: boolean;
}) {
  const unspecifiedLabel = labels.unspecifiedOption ?? "Not specified";
  const [countryCodes, setCountryCodes] = useState(() => {
    const codes = [...(query.countryCodes ?? [])];
    if (query.countryCode && !codes.includes(query.countryCode)) codes.unshift(query.countryCode);
    return codes;
  });
  const [updatedFrom, setUpdatedFrom] = useState(query.updatedFrom ?? "");
  const [updatedTo, setUpdatedTo] = useState(query.updatedTo ?? "");
  const countries = useMemo(
    () => [...new Set(services.flatMap((service) => service.country_codes))].sort(),
    [services],
  );
  const visibleServices = useMemo(() => {
    if (!countryCodes.length) return services;
    return services.filter((service) => {
      if (countryCodes.includes(CATALOG_UNSPECIFIED_FILTER) && service.country_codes.length === 0) {
        return true;
      }
      return service.country_codes.some((code) => countryCodes.includes(code));
    });
  }, [countryCodes, services]);
  const authorOptions = useMemo(
    () => sortAuthorOptions(authors, query.authors),
    [authors, query.authors],
  );
  const resourceValues = query.resource === "all" ? ["components", "setups"] : [query.resource];
  const verificationLabel = labels.verificationFilter ?? labels.verifiedOnly;
  const verificationOptions = [
    { value: "verified", label: labels.verifiedOption ?? labels.verifiedOnly },
    { value: "not_verified", label: labels.notVerifiedOption ?? "Not verified" },
  ];
  return (
    <div className="min-w-0 space-y-6">
      <div className="grid min-w-0 items-start gap-5 md:grid-cols-2">
        <Facet label={labels.resourceLegend}>
          <SearchableMultiSelect
            name="resource"
            label={labels.resourceLegend}
            searchLabel={labels.searchOptions}
            options={[
              { value: "components", label: labels.components },
              { value: "setups", label: labels.setups },
            ]}
            selected={resourceValues}
          />
        </Facet>
        {query.resource !== "setups" ? (
          <Facet
            label={labels.typeFilter}
            help={labels.typeFilterHelp ?? labels.filterHelpBody}
            helpLabel={labels.filterHelpLabel}
          >
            <SearchableMultiSelect
              name="component_types"
              label={labels.typeFilter}
              searchLabel={labels.searchOptions}
              options={COMPONENT_TYPE_FACETS}
              selected={
                query.componentTypes.length
                  ? query.componentTypes
                  : query.componentType
                    ? [query.componentType]
                    : []
              }
            />
          </Facet>
        ) : null}
        <Facet
          label={verificationLabel}
          help={labels.verificationHelp ?? labels.verifiedOnlyHelp ?? labels.filterHelpBody}
          helpLabel={labels.filterHelpLabel}
        >
          <SearchableMultiSelect
            name="verification"
            label={verificationLabel}
            searchLabel={labels.searchOptions}
            options={verificationOptions}
            selected={
              query.verification.length
                ? query.verification
                : query.verifiedOnly
                  ? ["verified"]
                  : []
            }
          />
        </Facet>
        <Facet
          label={labels.safetyPercentFilter ?? "Safety checks"}
          help={labels.safetyPercentHelp ?? labels.filterHelpBody}
          helpLabel={labels.filterHelpLabel}
        >
          <SearchableMultiSelect
            name="min_safety_percent"
            label={labels.safetyPercentFilter ?? "Safety checks"}
            searchLabel={labels.searchOptions}
            options={[75, 85, 90, 99].map((value) => ({
              value: String(value),
              label: `${value}%`,
            }))}
            selected={query.minSafetyPercent === undefined ? [] : [String(query.minSafetyPercent)]}
            multiple={false}
          />
        </Facet>
        <Facet
          label={labels.tagFilter}
          help={labels.tagFilterHelp ?? labels.filterHelpBody}
          helpLabel={labels.filterHelpLabel}
        >
          <SearchableMultiSelect
            name="tags"
            label={labels.tagFilter}
            searchLabel={labels.searchOptions}
            options={TAG_FACETS}
            selected={query.tags}
          />
        </Facet>
        <Facet
          label={labels.harnessFilter}
          help={labels.harnessFilterHelp ?? labels.filterHelpBody}
          helpLabel={labels.filterHelpLabel}
        >
          <SearchableMultiSelect
            name="harness_ids"
            label={labels.harnessFilter}
            searchLabel={labels.searchOptions}
            options={HARNESS_FACETS}
            selected={
              query.harnessIds.length ? query.harnessIds : query.harnessId ? [query.harnessId] : []
            }
          />
        </Facet>
        <LinkedRelationFacets
          labels={labels}
          unspecifiedLabel={unspecifiedLabel}
          countries={countries}
          locale={locale}
          countryCodes={countryCodes}
          onCountryChange={setCountryCodes}
          services={visibleServices}
          selectedServices={
            query.serviceDomains?.length
              ? query.serviceDomains
              : query.serviceDomain
                ? [query.serviceDomain]
                : []
          }
        />
        {hideAuthorFilter ? null : (
          <label className="min-w-0 space-y-2 text-sm">
            <span className="flex min-w-0 items-center gap-1 font-medium">
              {labels.authorFilter}
              <Help
                label={labels.filterHelpLabel}
                text={labels.authorFilterHelp ?? labels.filterHelpBody}
              />
            </span>
            <SearchableMultiSelect
              name="authors"
              label={labels.authorFilter}
              searchLabel={labels.authorSearch ?? labels.authorFilter}
              options={authorOptions}
              selected={query.authors}
              modal
              closeLabel={labels.closeFilters}
              selectionSuffix={labels.authorSelectionSuffix}
              emptyHint={labels.authorSelectionHint}
            />
          </label>
        )}
        <UpdatedRangeFields
          labels={labels}
          updatedFrom={updatedFrom}
          updatedTo={updatedTo}
          onFromChange={setUpdatedFrom}
          onToChange={setUpdatedTo}
        />
      </div>
    </div>
  );
}
function sortAuthorOptions(
  authors: readonly CatalogAuthorOption[],
  selected: readonly string[],
): Array<{ value: string; label: string; avatarUrl: string | null }> {
  const byId = new Map(authors.map((author) => [author.account_id, author]));
  for (const accountId of selected) {
    if (!byId.has(accountId)) {
      byId.set(accountId, {
        account_id: accountId,
        first_name: null,
        last_name: null,
        display_name: null,
        avatar_url: null,
      });
    }
  }
  return [...byId.values()]
    .map((author) => ({
      value: author.account_id,
      label:
        author.display_name ||
        [author.first_name, author.last_name].filter(Boolean).join(" ") ||
        author.account_id,
      avatarUrl: author.avatar_url,
    }))
    .sort((left, right) => {
      const leftBucket = authorScriptBucket(left.label);
      const rightBucket = authorScriptBucket(right.label);
      return (
        leftBucket - rightBucket ||
        AUTHOR_COLLATOR.compare(left.label, right.label) ||
        left.value.localeCompare(right.value)
      );
    });
}

const AUTHOR_COLLATOR = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

function authorScriptBucket(value: string): number {
  const first = value.trimStart().slice(0, 1);
  if (first && /[A-Za-z]/.test(first)) return 0;
  if (first && /[А-Яа-яЁё]/.test(first)) return 1;
  return 2;
}

function LinkedRelationFacets({
  labels,
  unspecifiedLabel,
  countries,
  locale,
  countryCodes,
  onCountryChange,
  services,
  selectedServices,
}: {
  labels: CatalogFilterPanelLabels;
  unspecifiedLabel: string;
  countries: string[];
  locale: string;
  countryCodes: string[];
  onCountryChange: (values: string[]) => void;
  services: ExternalProduct[];
  selectedServices: string[];
}) {
  return (
    <fieldset className="border-border min-w-0 space-y-3 rounded-lg border p-4 md:col-span-2">
      <legend className="px-1 text-sm font-medium">{labels.serviceFilter}</legend>
      <div className="grid min-w-0 gap-3 sm:grid-cols-2">
        <Facet
          label={labels.countryFilter}
          help={labels.countryFilterHelp ?? labels.filterHelpBody}
          helpLabel={labels.filterHelpLabel}
        >
          <SearchableMultiSelect
            name="country_codes"
            label={labels.countryFilter}
            searchLabel={labels.searchOptions}
            options={[
              { value: CATALOG_UNSPECIFIED_FILTER, label: unspecifiedLabel },
              ...countries.map((code) => ({
                value: code,
                label: localizedCountryName(code, locale),
              })),
            ]}
            selected={countryCodes}
            onChange={onCountryChange}
          />
        </Facet>
        <Facet
          label={labels.serviceFilter}
          help={labels.serviceFilterHelp ?? labels.filterHelpBody}
          helpLabel={labels.filterHelpLabel}
        >
          <SearchableMultiSelect
            key={countryCodes.slice().sort().join(",")}
            name="service_domains"
            label={labels.serviceFilter}
            searchLabel={labels.searchOptions}
            options={[
              { value: CATALOG_UNSPECIFIED_FILTER, label: unspecifiedLabel },
              ...services.map((service) => ({
                value: service.canonical_domain,
                label: service.name,
              })),
            ]}
            selected={selectedServices.filter(
              (domain) =>
                domain === CATALOG_UNSPECIFIED_FILTER ||
                services.some((service) => service.canonical_domain === domain),
            )}
          />
        </Facet>
      </div>
    </fieldset>
  );
}

function UpdatedRangeFields({
  labels,
  updatedFrom,
  updatedTo,
  onFromChange,
  onToChange,
}: {
  labels: CatalogFilterPanelLabels;
  updatedFrom: string;
  updatedTo: string;
  onFromChange: (value: string) => void;
  onToChange: (value: string) => void;
}) {
  return (
    <fieldset className="min-w-0 space-y-2">
      <legend className="flex items-center gap-1 text-sm font-medium">
        {labels.updatedFrom ?? "Updated from"} / {labels.updatedTo ?? "Updated to"}
        {labels.updatedRangeHelp ? (
          <Help label={labels.filterHelpLabel} text={labels.updatedRangeHelp} />
        ) : null}
      </legend>
      <details className="border-input bg-background min-w-0 rounded-sm border">
        <summary className="flex min-h-11 cursor-pointer list-none items-center px-3 text-sm break-all marker:content-none">
          {updatedFrom || updatedTo
            ? `${updatedFrom || "…"} — ${updatedTo || "…"}`
            : `${labels.updatedFrom ?? "Updated from"} — ${labels.updatedTo ?? "Updated to"}`}
        </summary>
        <div className="border-border grid gap-3 border-t p-3 sm:grid-cols-2">
          <label className="space-y-1 text-xs font-medium">
            <span>{labels.updatedFrom ?? "Updated from"}</span>
            <input
              type="date"
              name="updated_from"
              value={updatedFrom}
              onChange={(event) => {
                onFromChange(event.target.value);
              }}
              className={selectClassName}
            />
          </label>
          <label className="space-y-1 text-xs font-medium">
            <span>{labels.updatedTo ?? "Updated to"}</span>
            <input
              type="date"
              name="updated_to"
              value={updatedTo}
              onChange={(event) => {
                onToChange(event.target.value);
              }}
              className={selectClassName}
            />
          </label>
        </div>
      </details>
      {updatedFrom || updatedTo ? (
        <button
          type="button"
          className="text-muted-foreground text-xs underline underline-offset-4"
          onClick={() => {
            onFromChange("");
            onToChange("");
          }}
        >
          {labels.clearUpdatedRange ?? "Clear dates"}
        </button>
      ) : null}
    </fieldset>
  );
}

function Facet({
  label,
  help,
  helpLabel,
  children,
}: {
  label: string;
  help?: string;
  helpLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-w-0 space-y-2 text-sm">
      <span className="flex min-w-0 items-center gap-1 font-medium">
        {label}
        {help ? <Help label={helpLabel ?? label} text={help} /> : null}
      </span>
      {children}
    </div>
  );
}

function Help({ label, text }: { label: string; text: string }) {
  return (
    <button
      type="button"
      className="group/help text-muted-foreground hover:bg-muted focus-visible:ring-ring relative inline-grid size-6 shrink-0 place-items-center rounded-sm focus-visible:ring-2"
      aria-label={label}
    >
      <span aria-hidden="true" className="text-xs font-semibold">
        ?
      </span>
      <span
        role="tooltip"
        className="border-border bg-popover text-popover-foreground pointer-events-none absolute bottom-full left-0 z-[70] mb-2 hidden w-[min(14rem,calc(100vw-2.5rem))] rounded-md border p-2 text-left text-xs font-normal shadow-md group-hover/help:block group-focus/help:block"
      >
        {text}
      </span>
    </button>
  );
}
