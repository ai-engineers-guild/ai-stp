import { getTranslations, setRequestLocale } from "next-intl/server";

import { CliCopyBlock } from "@/components/molecules/cli-copy-block";
import { StatePanel } from "@/components/molecules/state-panel";
import { CatalogFilters } from "@/components/organisms/catalog-filters";
import { CatalogResults } from "@/components/organisms/catalog-results";
import { OwnerObjectActions } from "@/components/organisms/owner-object-actions";
import { listCatalogAuthors, listExternalProducts } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/errors";
import { listOwnerObjects } from "@/lib/api/owner";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { filterAndSortOwnerObjects } from "@/lib/owner-catalog";
import { ownerComponentNextStep, ownerSetupNextStep } from "@/lib/cli-copy";
import { parseCatalogSearchParams, catalogQueryToRecord } from "@/lib/catalog-query";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function catalogParams(
  raw: Record<string, string | string[] | undefined>,
): Record<string, string | string[] | undefined> {
  const { kind, ...rest } = raw;
  if (rest.resource || !kind) return rest;
  return { ...rest, resource: kind === "component" ? "components" : "setups" };
}

// Owner workspace intentionally uses the catalog browser and card projection so
// private rows differ only by access and actions, not by presentation.
// eslint-disable-next-line max-lines-per-function
export default async function OwnerObjectsPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const raw = await searchParams;
  const session = await requireSession(locale, `/${locale}/objects`);
  const token = (await sessionCookieValue()) ?? "";
  const csrfToken = (await readCsrfToken()) ?? "";
  const t = await getTranslations("objects");
  const tc = await getTranslations("common");
  const tCli = await getTranslations("cli");
  const tCatalog = await getTranslations("catalog");
  const parsed = parseCatalogSearchParams(catalogParams(raw));

  if (!parsed.ok) {
    return <StatePanel kind="error" title={tc("error")} description={tCatalog("filterError")} />;
  }
  const query = parsed.value;

  let ownerObjects;
  try {
    ownerObjects = await listOwnerObjects(token, { page_size: 100 });
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  const [services, authors] = await Promise.all([
    listExternalProducts()
      .then((result) => result.items)
      .catch(() => []),
    listCatalogAuthors()
      .then((result) => result.items)
      .catch(() => []),
  ]);
  const items = filterAndSortOwnerObjects(ownerObjects.items, query);
  const ownerActions = Object.fromEntries(
    items.map((item) => [
      `${item.object_kind}:${item.stable_id}`,
      <OwnerObjectActions
        key={`${item.object_kind}:${item.stable_id}`}
        csrfToken={csrfToken}
        deviceId={session.deviceId}
        kind={item.object_kind}
        stableId={item.stable_id}
        name={item.name}
        version={item.latest_version}
        visibility={item.visibility}
      />,
    ]),
  );
  const labels = {
    authoritative: tCatalog("authoritative"),
    experimental: tCatalog("experimental"),
    experimentalNote: tCatalog("experimentalNote"),
    emptyAuthoritative: tCatalog("emptyAuthoritative"),
    emptyExperimental: tCatalog("emptyExperimental"),
    emptyAll: tCatalog("emptyAll"),
    resultsHeading: tCatalog("mixedResults"),
    nextPage: tCatalog("nextPage"),
    version: tCatalog("version"),
    harness: tCatalog("harness"),
    type: tCatalog("type"),
    tags: tCatalog("tags"),
    purpose: tCatalog("purpose"),
    targetRole: tCatalog("targetRole"),
    authorVerified: tCatalog("authorVerified"),
    authorVerifiedDescription: tCatalog("authorVerifiedDescription"),
    githubStars: tCatalog("githubStars"),
    componentVerified: tCatalog("componentVerified"),
    yes: tc("yes"),
    no: tc("no"),
    publisher: tCatalog("publisher"),
    publishedAt: tCatalog("updatedAt"),
    likes: tCatalog("likes"),
    detailViews: tCatalog("detailViews"),
    artifactDownloads: tCatalog("artifactDownloads"),
    componentKind: tCatalog("componentKind"),
    setupKind: tCatalog("setupKind"),
    publicVisibility: tCatalog("public"),
    privateVisibility: tCatalog("private"),
    supportTier: tCatalog("supportTier"),
    supportState: tCatalog("supportState"),
    supportEvidence: tCatalog("supportEvidence"),
    noSupportEvidence: tCatalog("noSupportEvidence"),
    moreActions: tCatalog("moreActions"),
    copyCli: tCatalog("copyCli"),
    copyId: tCatalog("copyId"),
    copyUrl: tCatalog("copyUrl"),
    copied: tCatalog("copied"),
    report: tCatalog("report"),
    reportSetup: tCatalog("reportSetup"),
    pagination: tCatalog("pagination"),
    whyFailed: tCatalog("whyFailed"),
    whyWarning: tCatalog("whyWarning"),
    whyOptionalFailed: tCatalog("whyOptionalFailed"),
    safetyChecks: tCatalog("safetyChecks"),
    requirements: tCatalog("requirements"),
    credentialsRequired: tCatalog("credentialsRequired"),
    safetyStatus: tCatalog("safetyStatus"),
    safetyPercent: tCatalog("safetyPercent"),
    safetyPassed: tCatalog("safetyPassed"),
    safetyFailed: tCatalog("safetyFailed"),
    safetyWarning: tCatalog("safetyWarning"),
    safetyNotRun: tCatalog("safetyNotRun"),
    safetyIncomplete: tCatalog("safetyIncomplete"),
    safetyEmpty: tCatalog("safetyEmpty"),
    safetyNoScan: tCatalog("safetyNoScan"),
    safetyAvailable: tCatalog("safetyAvailable"),
    safetyPending: tCatalog("safetyPending"),
    safetyMandatory: tCatalog("safetyMandatory"),
    safetyCheckExplanation: tCatalog("safetyCheckExplanation"),
    like: tCatalog("like"),
    unlike: tCatalog("unlike"),
    likeMenu: tCatalog("likeMenu"),
    unlikeMenu: tCatalog("unlikeMenu"),
    assuranceCounts: tCatalog("assuranceCounts"),
    familyMemberCount: tCatalog("familyMemberCount"),
  };

  return (
    <div className="min-w-0 space-y-8 overflow-x-hidden">
      <div className="min-w-0 space-y-4">
        <h1 className="text-2xl font-medium tracking-tight break-words sm:text-3xl">
          {t("title")}
        </h1>
        <p className="text-muted-foreground max-w-2xl text-sm">{t("subtitle")}</p>
        <CatalogFilters
          query={query}
          locale={locale}
          basePath="/objects"
          services={services}
          authors={authors}
          intro={tCatalog("scopedFilterDescription")}
          labels={{
            search: tCatalog("search"),
            searchPlaceholder: tCatalog("searchPlaceholder"),
            searchHelp: tCatalog("searchHelp"),
            queryFields: tCatalog("queryFields"),
            queryOperators: tCatalog("queryOperators"),
            queryLiteralHint: tCatalog("queryLiteralHint"),
            resourceLegend: tCatalog("resourceLegend"),
            components: tCatalog("components"),
            setups: tCatalog("setups"),
            resourceBoth: tCatalog("resourceBoth"),
            experimentalConsent: tCatalog("experimentalConsent"),
            tagFilter: tCatalog("tagFilter"),
            harnessFilter: tCatalog("harnessFilter"),
            typeFilter: tCatalog("typeFilter"),
            supportTierFilter: tCatalog("supportTierFilter"),
            supportStateFilter: tCatalog("supportStateFilter"),
            anyOption: tCatalog("anyOption"),
            applyFilters: tCatalog("applyFilters"),
            filtersButton: tCatalog("filtersButton"),
            resetAll: tCatalog("resetAll"),
            filterHelpTitle: tCatalog("filterHelpTitle"),
            filterHelpBody: tCatalog("filterHelpBody"),
            dismissFilter: tCatalog("dismissFilter"),
            closeFilters: tCatalog("closeFilters"),
            filterHelpLabel: tCatalog("filterHelpLabel"),
            tagFilterHelp: tCatalog("tagFilterHelp"),
            harnessFilterHelp: tCatalog("harnessFilterHelp"),
            typeFilterHelp: tCatalog("typeFilterHelp"),
            authorFilterHelp: tCatalog("authorFilterHelp"),
            verificationHelp: tCatalog("verificationHelp"),
            safetyPercentHelp: tCatalog("safetyPercentHelp"),
            verifiedOnlyHelp: tCatalog("verifiedOnlyHelp"),
            countryFilterHelp: tCatalog("countryFilterHelp"),
            serviceFilterHelp: tCatalog("serviceFilterHelp"),
            updatedRangeHelp: tCatalog("updatedRangeHelp"),
            searchOptions: tCatalog("searchOptions"),
            authorFilter: tCatalog("authorFilter"),
            authorSearch: tCatalog("authorSearch"),
            authorSelectionSuffix: tCatalog("authorSelected"),
            authorSelectionHint: tCatalog("authorSelectionHint"),
            verificationFilter: tCatalog("verificationFilter"),
            verifiedOption: tCatalog("verifiedOption"),
            notVerifiedOption: tCatalog("notVerifiedOption"),
            safetyPercentFilter: tCatalog("safetyPercentFilter"),
            verifiedOnly: tCatalog("verifiedOnly"),
            serviceFilter: tCatalog("serviceFilter"),
            countryFilter: tCatalog("countryFilter"),
            unspecifiedOption: tCatalog("unspecifiedOption"),
            updatedFrom: tCatalog("updatedFrom"),
            updatedTo: tCatalog("updatedTo"),
            clearUpdatedRange: tCatalog("clearUpdatedRange"),
            sortBy: tCatalog("sortBy"),
            sortDirection: tCatalog("sortDirection"),
            sortRelevance: tCatalog("sortRelevance"),
            sortUpdated: tCatalog("sortUpdated"),
            sortLikes: tCatalog("sortLikes"),
            sortAscending: tCatalog("sortAscending"),
            sortDescending: tCatalog("sortDescending"),
            viewLabel: tCatalog("viewLabel"),
            cardsView: tCatalog("cardsView"),
            listView: tCatalog("listView"),
            refineButton: tCatalog("refineButton"),
            queryCorrection: tCatalog("queryCorrection"),
            updatingLabel: tCatalog("updating"),
          }}
        />
      </div>
      {items.length === 0 ? (
        <div className="space-y-4">
          <StatePanel
            kind="empty"
            title={tCli("ownerEmptyTitle")}
            description={tCli("ownerEmptyBody")}
          />
          <CliCopyBlock
            command={ownerComponentNextStep()}
            title={tCli("syncCommandHint")}
            copyLabel={tCli("copy")}
            copiedLabel={tCli("copied")}
            errorLabel={tCli("copyError")}
            docsLabel={tCli("docs")}
          />
          <CliCopyBlock
            command={ownerSetupNextStep()}
            title={tCli("setupNextStepHint")}
            copyLabel={tCli("copy")}
            copiedLabel={tCli("copied")}
            errorLabel={tCli("copyError")}
            docsLabel={tCli("docs")}
          />
        </div>
      ) : (
        <CatalogResults
          kind="mixed"
          items={[]}
          experimental={[]}
          nextCursor={null}
          totalItems={items.length}
          view={query.view}
          showExperimental={false}
          basePath="/objects"
          query={catalogQueryToRecord(query)}
          labels={labels}
          locale={locale}
          ownerItems={items}
          ownerActions={ownerActions}
        />
      )}
    </div>
  );
}
