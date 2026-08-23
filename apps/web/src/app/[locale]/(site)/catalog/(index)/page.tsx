import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { CatalogFilters } from "@/components/organisms/catalog-filters";
import { CatalogResults } from "@/components/organisms/catalog-results";
import type { CatalogAuthor } from "@/components/organisms/object-card";
import { ApiError } from "@/lib/api/errors";
import { listCatalogReactions } from "@/lib/api/reactions";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { loadPublisherProfiles, startCatalogResourceReads } from "@/lib/catalog-load";
import { catalogQueryToRecord, parseCatalogSearchParams } from "@/lib/catalog-query";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("catalog");
  const description = t("seoDescription");
  return {
    title: t("title"),
    description,
    keywords: ["MCP", "skills", "hooks", "subagents", "AI setups", "plugins"],
    openGraph: { title: t("title"), description },
    twitter: { title: t("title"), description },
  };
}

// The page intentionally owns validation, both resource projections, and localized presentation.
// eslint-disable-next-line max-lines-per-function, complexity
export default async function CatalogPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const sp = await searchParams;
  const t = await getTranslations("catalog");
  const tc = await getTranslations("common");

  const parsed = parseCatalogSearchParams(sp);
  if (!parsed.ok) {
    const details = [
      ...parsed.unknownKeys.map((key) => `${t("unknownFilter")}: ${key}`),
      ...parsed.invalidTags.map((tag) => `${t("invalidTag")}: ${tag}`),
      ...parsed.invalidSupport.map((filter) => `${t("invalidSupport")}: ${filter}`),
      ...parsed.invalidQuery.map((error) => `${t("invalidQuery")}: ${error}`),
    ].join("; ");
    return (
      <div className="space-y-8">
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <StatePanel kind="error" title={t("filterError")} description={details} />
      </div>
    );
  }

  const query = parsed.value;
  const { resource, includeExperimental, pageNumber, setupsPage, componentsPage } = query;
  const setupsPageNumber = setupsPage ?? pageNumber;
  const componentsPageNumber = componentsPage ?? pageNumber;

  let errorMessage: string | null = null;
  let componentItems = [] as NonNullable<
    Awaited<ReturnType<typeof startCatalogResourceReads>["components"]>
  >["items"];
  let componentExperimental = [] as NonNullable<
    Awaited<ReturnType<typeof startCatalogResourceReads>["components"]>
  >["experimental"];
  let setupItems = [] as NonNullable<
    Awaited<ReturnType<typeof startCatalogResourceReads>["setups"]>
  >["items"];
  let setupExperimental = [] as NonNullable<
    Awaited<ReturnType<typeof startCatalogResourceReads>["setups"]>
  >["experimental"];
  let nextCursor: string | null = null;
  let totalItems: number | null = null;
  let totalPages: number | null = null;
  let setupTotalItems: number | null = null;
  let setupTotalPages: number | null = null;
  let componentTotalItems: number | null = null;
  let componentTotalPages: number | null = null;
  let authorProfiles: Record<string, CatalogAuthor> = {};
  const started = startCatalogResourceReads(query);
  const services = await started.services;

  try {
    const [componentResult, setupResult] = await Promise.all([started.components, started.setups]);
    if (componentResult) {
      componentItems = componentResult.items;
      componentExperimental = componentResult.experimental;
      if (resource !== "all") nextCursor = componentResult.page.next_cursor;
      const pageMeta = componentResult.page;
      componentTotalItems = typeof pageMeta.total_items === "number" ? pageMeta.total_items : null;
      componentTotalPages = typeof pageMeta.total_pages === "number" ? pageMeta.total_pages : null;
      totalItems = componentTotalItems;
      totalPages = componentTotalPages;
    }
    if (setupResult) {
      setupItems = setupResult.items;
      setupExperimental = setupResult.experimental;
      if (resource !== "all") nextCursor = setupResult.page.next_cursor;
      const pageMeta = setupResult.page;
      setupTotalItems = typeof pageMeta.total_items === "number" ? pageMeta.total_items : null;
      setupTotalPages = typeof pageMeta.total_pages === "number" ? pageMeta.total_pages : null;
      if (resource === "setups") {
        totalItems = setupTotalItems;
        totalPages = setupTotalPages;
      }
    }
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_VALIDATION_ERROR") {
      errorMessage = t("filterError");
    } else {
      errorMessage =
        error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE"
          ? tc("apiUnavailable")
          : tc("error");
    }
  }

  if (!errorMessage) {
    authorProfiles = await loadPublisherProfiles(
      [...componentItems, ...componentExperimental, ...setupItems, ...setupExperimental].map(
        (item) => item.publisher_id,
      ),
    );
  }

  const labels = {
    authoritative: t("authoritative"),
    experimental: t("experimental"),
    experimentalNote: t("experimentalNote"),
    emptyAuthoritative: t("emptyAuthoritative"),
    emptyExperimental: t("emptyExperimental"),
    emptyAll: t("emptyAll"),
    resultsHeading:
      resource === "all"
        ? t("mixedResults")
        : resource === "setups"
          ? t("setupsResults")
          : t("componentsResults"),
    nextPage: t("nextPage"),
    version: t("version"),
    harness: t("harness"),
    type: t("type"),
    tags: t("tags"),
    purpose: t("purpose"),
    targetRole: t("targetRole"),
    authorVerified: t("authorVerified"),
    authorVerifiedDescription: t("authorVerifiedDescription"),
    githubStars: t("githubStars"),
    componentVerified: t("componentVerified"),
    yes: tc("yes"),
    no: tc("no"),
    publisher: t("publisher"),
    publishedAt: t("updatedAt"),
    likes: t("likes"),
    detailViews: t("detailViews"),
    artifactDownloads: t("artifactDownloads"),
    componentKind: t("componentKind"),
    setupKind: t("setupKind"),
    supportTier: t("supportTier"),
    supportState: t("supportState"),
    supportEvidence: t("supportEvidence"),
    noSupportEvidence: t("noSupportEvidence"),
    moreActions: t("moreActions"),
    copyCli: t("copyCli"),
    copyId: t("copyId"),
    copyUrl: t("copyUrl"),
    copied: t("copied"),
    report: t("report"),
    reportSetup: t("reportSetup"),
    setupsHeading: t("setupsResults"),
    componentsHeading: t("componentsResults"),
    emptySetups: t("emptySetups"),
    emptyComponents: t("emptyComponents"),
    pagination: t("pagination"),
    setupsPagination: t("setupsPagination"),
    componentsPagination: t("componentsPagination"),
    whyFailed: t("whyFailed"),
    whyWarning: t("whyWarning"),
    safetyChecks: t("safetyChecks"),
    requirements: t("requirements"),
    credentialsRequired: t("credentialsRequired"),
    safetyStatus: t("safetyStatus"),
    safetyPercent: t("safetyPercent"),
    safetyPassed: t("safetyPassed"),
    safetyFailed: t("safetyFailed"),
    safetyWarning: t("safetyWarning"),
    safetyNotRun: t("safetyNotRun"),
    safetyIncomplete: t("safetyIncomplete"),
    safetyEmpty: t("safetyEmpty"),
    safetyNoScan: t("safetyNoScan"),
    safetyAvailable: t("safetyAvailable"),
    safetyPending: t("safetyPending"),
    safetyMandatory: t("safetyMandatory"),
    safetyCheckExplanation: t("safetyCheckExplanation"),
    like: t("like"),
    unlike: t("unlike"),
    likeMenu: t("likeMenu"),
    unlikeMenu: t("unlikeMenu"),
  };

  let likedIds: string[] = [];
  const sessionToken = await sessionCookieValue();
  if (sessionToken) {
    try {
      const reactions = await listCatalogReactions(sessionToken);
      likedIds = reactions.items.map((item) => item.summary.stable_id);
    } catch {
      likedIds = [];
    }
  }

  return (
    <div className="min-w-0 space-y-8 overflow-x-hidden">
      <div className="min-w-0 space-y-4">
        <h1 className="text-2xl font-medium tracking-tight break-words sm:text-3xl">
          {t("title")}
        </h1>
        <CatalogFilters
          query={query}
          locale={locale}
          services={services}
          intro={t("subtitle")}
          labels={{
            search: t("search"),
            searchPlaceholder: t("searchPlaceholder"),
            searchHelp: t("searchHelp"),
            resourceLegend: t("resourceLegend"),
            components: t("components"),
            setups: t("setups"),
            resourceBoth: t("resourceBoth"),
            experimentalConsent: t("experimentalConsent"),
            tagFilter: t("tagFilter"),
            harnessFilter: t("harnessFilter"),
            typeFilter: t("typeFilter"),
            supportTierFilter: t("supportTierFilter"),
            supportStateFilter: t("supportStateFilter"),
            anyOption: t("anyOption"),
            applyFilters: t("applyFilters"),
            filtersButton: t("filtersButton"),
            resetAll: t("resetAll"),
            filterHelpTitle: t("filterHelpTitle"),
            filterHelpBody: t("filterHelpBody"),
            dismissFilter: t("dismissFilter"),
            closeFilters: t("closeFilters"),
            filterHelpLabel: t("filterHelpLabel"),
            tagFilterHelp: t("tagFilterHelp"),
            harnessFilterHelp: t("harnessFilterHelp"),
            typeFilterHelp: t("typeFilterHelp"),
            authorFilterHelp: t("authorFilterHelp"),
            verifiedOnlyHelp: t("verifiedOnlyHelp"),
            countryFilterHelp: t("countryFilterHelp"),
            serviceFilterHelp: t("serviceFilterHelp"),
            updatedRangeHelp: t("updatedRangeHelp"),
            searchOptions: t("searchOptions"),
            authorFilter: t("authorFilter"),
            verifiedOnly: t("verifiedOnly"),
            serviceFilter: t("serviceFilter"),
            countryFilter: t("countryFilter"),
            unspecifiedOption: t("unspecifiedOption"),
            updatedFrom: t("updatedFrom"),
            updatedTo: t("updatedTo"),
            clearUpdatedRange: t("clearUpdatedRange"),
            sortBy: t("sortBy"),
            sortDirection: t("sortDirection"),
            sortRelevance: t("sortRelevance"),
            sortUpdated: t("sortUpdated"),
            sortLikes: t("sortLikes"),
            sortAscending: t("sortAscending"),
            sortDescending: t("sortDescending"),
            viewLabel: t("viewLabel"),
            cardsView: t("cardsView"),
            listView: t("listView"),
            refineButton: t("refineButton"),
            queryCorrection: t("queryCorrection"),
            updatingLabel: t("updating"),
          }}
        />
      </div>
      {errorMessage ? (
        <StatePanel kind="error" title={tc("error")} description={errorMessage} />
      ) : (
        <CatalogResults
          kind={resource === "all" ? "mixed" : resource}
          items={
            resource === "all"
              ? [...setupItems, ...componentItems]
              : resource === "setups"
                ? setupItems
                : componentItems
          }
          experimental={
            resource === "all"
              ? [...setupExperimental, ...componentExperimental]
              : resource === "setups"
                ? setupExperimental
                : componentExperimental
          }
          nextCursor={resource === "all" ? null : nextCursor}
          totalItems={
            resource === "all"
              ? (setupTotalItems ?? setupItems.length) +
                (componentTotalItems ?? componentItems.length)
              : totalItems
          }
          totalPages={resource === "all" ? null : totalPages}
          pageNumber={pageNumber}
          setupsPageNumber={setupsPageNumber}
          componentsPageNumber={componentsPageNumber}
          setupsTotalPages={setupTotalPages}
          componentsTotalPages={componentTotalPages}
          setupsTotalItems={setupTotalItems}
          componentsTotalItems={componentTotalItems}
          view={query.view}
          showExperimental={includeExperimental}
          basePath="/catalog"
          query={catalogQueryToRecord(query)}
          labels={labels}
          locale={locale}
          authors={authorProfiles}
          likedIds={likedIds}
        />
      )}
    </div>
  );
}
