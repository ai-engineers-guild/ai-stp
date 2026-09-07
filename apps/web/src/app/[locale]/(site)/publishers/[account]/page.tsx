import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Badge } from "@/components/atoms/badge";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { CatalogFilters } from "@/components/organisms/catalog-filters";
import { CatalogResults } from "@/components/organisms/catalog-results";
import { PublisherActions } from "@/components/organisms/publisher-actions";
import { StatePanel } from "@/components/molecules/state-panel";
import { VerifiedAvatar } from "@/components/molecules/verified-avatar";
import { ApiError } from "@/lib/api/errors";
import { readPublisherProfile, readPublisherStats } from "@/lib/api/public-profile";
import { asAccountId } from "@/lib/brands";
import { catalogQueryToRecord, parseCatalogSearchParams } from "@/lib/catalog-query";
import { startCatalogResourceReads } from "@/lib/catalog-load";
import { buildDeepLink, normalizeTarget } from "@/lib/deep-links";
import { readSession } from "@/lib/auth/session";
import { publicOrigin } from "@/lib/site";
import { renderMarkdownOnServer } from "@/lib/markdown/render";
import { Icon } from "@/theme";

function linkHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function ProfileLinks({ links }: { links: ReadonlyArray<{ label: string; url: string }> }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {links.map((link) => (
        <li key={`${link.label}-${link.url}`}>
          <a
            href={link.url}
            className="border-border hover:bg-muted focus-visible:ring-ring inline-flex min-w-0 items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
            rel="noopener noreferrer"
            target="_blank"
          >
            <span className="font-medium">{link.label}</span>
            <span className="text-muted-foreground max-w-44 truncate font-mono text-xs">
              {linkHost(link.url)}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

function ProfileStat({
  icon,
  label,
  value,
}: {
  icon: "cards" | "heart" | "eye";
  label: string;
  value: number;
}) {
  return (
    <span
      className="group/stat text-muted-foreground hover:text-foreground relative inline-flex items-center gap-1.5 rounded-sm text-sm transition-colors"
      title={`${label}: ${value.toLocaleString()}`}
      aria-label={`${label}: ${value.toLocaleString()}`}
    >
      <Icon name={icon} size="sm" />
      <span className="font-mono text-xs tabular-nums">{value.toLocaleString()}</span>
      <span
        role="tooltip"
        className="border-border bg-popover text-popover-foreground pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 hidden -translate-x-1/2 rounded-md border px-2 py-1 text-xs whitespace-nowrap shadow-md group-hover/stat:block"
      >
        {label}
      </span>
    </span>
  );
}

type PageProps = {
  params: Promise<{ locale: string; account: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/** Public publisher profile (SPEC-028 / REQ-2210). Published allowlist only. */
// The page intentionally keeps profile and the catalog's mixed resource view together.
// eslint-disable-next-line max-lines-per-function, complexity
export default async function PublisherPage({ params, searchParams }: PageProps) {
  const { locale, account } = await params;
  const sp = await searchParams;
  setRequestLocale(locale);
  const t = await getTranslations("publisher");
  const tc = await getTranslations("common");
  const tCatalog = await getTranslations("catalog");
  const tContact = await getTranslations("contact");
  const tAccount = await getTranslations("account");
  const session = await readSession();

  const accountId = (() => {
    try {
      return asAccountId(account);
    } catch {
      notFound();
    }
  })();

  let profile;
  try {
    profile = await readPublisherProfile(accountId);
  } catch {
    notFound();
  }

  const parsed = parseCatalogSearchParams({
    ...sp,
    q: undefined,
    resource: "all",
    authors: accountId,
  });
  if (!parsed.ok) {
    return <StatePanel kind="error" title={tc("error")} description={tCatalog("filterError")} />;
  }
  const query = parsed.value;
  const started = startCatalogResourceReads(query);
  const [services, stats] = await Promise.all([
    started.services,
    readPublisherStats(accountId).catch(() => null),
  ]);
  let errorMessage: string | null = null;
  let components: Awaited<typeof started.components> = null;
  let setups: Awaited<typeof started.setups> = null;
  try {
    [components, setups] = await Promise.all([started.components, started.setups]);
    if (!components || !setups) throw new Error("catalog resource unavailable");
  } catch (error) {
    errorMessage =
      error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE"
        ? tc("apiUnavailable")
        : tc("error");
    components = null;
    setups = null;
  }

  const isEmpty =
    Boolean(profile.empty) ||
    (profile.display_name === null &&
      profile.bio === null &&
      profile.links.length === 0 &&
      !profile.avatar_url);
  const isOwner = session?.accountId === accountId;
  let publisherLink: string | null = null;
  try {
    publisherLink = buildDeepLink(
      publicOrigin().origin,
      normalizeTarget({
        kind: "publisher",
        stable_id: accountId,
        locale: locale === "en" ? "en" : "ru",
      }),
    ).cli_command;
  } catch {
    publisherLink = null;
  }

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
    setupsHeading: tCatalog("setupsResults"),
    componentsHeading: tCatalog("componentsResults"),
    emptySetups: tCatalog("emptySetups"),
    emptyComponents: tCatalog("emptyComponents"),
    pagination: tCatalog("pagination"),
    setupsPagination: tCatalog("setupsPagination"),
    componentsPagination: tCatalog("componentsPagination"),
    whyFailed: tCatalog("whyFailed"),
    whyWarning: tCatalog("whyWarning"),
    whyOptionalFailed: tCatalog("whyOptionalFailed"),
    safetyChecks: tCatalog("safetyChecks"),
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
    requirements: tCatalog("requirements"),
    credentialsRequired: tCatalog("credentialsRequired"),
    like: tCatalog("like"),
    unlike: tCatalog("unlike"),
    likeMenu: tCatalog("likeMenu"),
    unlikeMenu: tCatalog("unlikeMenu"),
  };

  return (
    <article className="space-y-8">
      <HistoryBackButton label={tCatalog("backToCatalog")} fallback="/catalog" />
      <section className="border-border relative grid gap-6 border-b pb-8 sm:grid-cols-[auto_minmax(0,1fr)] sm:items-center">
        <VerifiedAvatar
          src={profile.avatar_url}
          verified={profile.author_verified}
          verifiedLabel={tCatalog("authorVerified")}
          size="lg"
          fallback={(profile.display_name ?? profile.account_id).slice(0, 2).toUpperCase()}
        />
        <div className="min-w-0 space-y-3">
          <div className="flex min-w-0 flex-wrap items-center gap-3 pr-14">
            <h1 className="min-w-0 text-3xl font-medium tracking-tight break-words">
              {profile.display_name ?? t("title")}
            </h1>
            {profile.author_verified ? (
              <Badge variant="success">{tCatalog("authorVerified")}</Badge>
            ) : null}
          </div>
          <div className="flex min-w-0 flex-wrap items-center gap-x-5 gap-y-2 pr-14">
            {stats ? (
              <>
                <ProfileStat icon="cards" label={t("objectsStat")} value={stats.total_objects} />
                <ProfileStat icon="heart" label={t("likesStat")} value={stats.likes_count} />
                <ProfileStat
                  icon="eye"
                  label={t("viewsAndDownloadsStat")}
                  value={stats.detail_views_count + stats.artifact_downloads_count}
                />
              </>
            ) : null}
          </div>
          {!isEmpty ? (
            <>
              {profile.links.length > 0 ? <ProfileLinks links={profile.links} /> : null}
              {profile.bio ? (
                <div
                  className="prose prose-sm text-muted-foreground max-w-prose text-sm leading-relaxed [&_a]:underline [&_code]:font-mono [&_pre]:overflow-x-auto [&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto"
                  dangerouslySetInnerHTML={{ __html: renderMarkdownOnServer(profile.bio).html }}
                />
              ) : null}
            </>
          ) : (
            <p className="text-muted-foreground">{t("emptyProfile")}</p>
          )}
        </div>
        <div className="absolute top-0 right-0">
          <PublisherActions
            accountId={profile.account_id}
            cliCommand={publisherLink}
            {...(isOwner ? { editHref: "/account/profile" } : {})}
            reportHref={`/reports?topic=author_complaint&author=${encodeURIComponent(profile.account_id)}`}
            labels={{
              more: tCatalog("moreActions"),
              report: tContact("reportAuthorType"),
              copyLink: tCatalog("copyUrl"),
              copyId: tCatalog("copyId"),
              useCli: tCatalog("copyCli"),
              editProfile: tAccount("profileEdit"),
              copied: tCatalog("copied"),
            }}
          />
        </div>
      </section>

      <section className="space-y-4" aria-labelledby="published-objects-heading">
        <div>
          <h2 id="published-objects-heading" className="text-xl font-medium tracking-tight">
            {t("publishedObjects")}
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            {tCatalog("scopedFilterDescription")}
          </p>
        </div>
        <CatalogFilters
          query={query}
          locale={locale}
          basePath={`/publishers/${encodeURIComponent(account)}`}
          hideSearch
          hideAuthorFilter
          fixedAuthors={[accountId]}
          services={services}
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
            verifiedOnlyHelp: tCatalog("verifiedOnlyHelp"),
            countryFilterHelp: tCatalog("countryFilterHelp"),
            serviceFilterHelp: tCatalog("serviceFilterHelp"),
            updatedRangeHelp: tCatalog("updatedRangeHelp"),
            searchOptions: tCatalog("searchOptions"),
            authorFilter: tCatalog("authorFilter"),
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
        {errorMessage ? (
          <StatePanel kind="error" title={tc("error")} description={errorMessage} />
        ) : components && setups ? (
          <CatalogResults
            kind="mixed"
            items={[...setups.items, ...components.items]}
            experimental={[...setups.experimental, ...components.experimental]}
            nextCursor={null}
            totalItems={
              (numberOrNull(setups.page.total_items) ?? setups.items.length) +
              (numberOrNull(components.page.total_items) ?? components.items.length)
            }
            pageNumber={query.pageNumber}
            setupsTotalPages={numberOrNull(setups.page.total_pages)}
            componentsTotalPages={numberOrNull(components.page.total_pages)}
            view={query.view}
            showExperimental={query.includeExperimental}
            basePath={`/publishers/${encodeURIComponent(account)}`}
            query={catalogQueryToRecord(query)}
            labels={labels}
            locale={locale}
            authors={{
              [accountId]: { displayName: profile.display_name, avatarUrl: profile.avatar_url },
            }}
          />
        ) : null}
      </section>
    </article>
  );
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
