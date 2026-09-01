import { ObjectCard, type CatalogAuthor } from "@/components/organisms/object-card";
import { StatePanel } from "@/components/molecules/state-panel";
import type { ComponentSummary, SetupSummary } from "@/lib/api/generated/types.gen";
import { PageNav, SingleResourcePager } from "@/components/organisms/catalog-page-nav";
import { catalogHref } from "@/lib/catalog-query";
import { UI } from "@/lib/ui-selectors";

type CatalogLabels = {
  authoritative: string;
  experimental: string;
  experimentalNote: string;
  emptyAuthoritative: string;
  emptyExperimental: string;
  emptyAll: string;
  resultsHeading: string;
  nextPage: string;
  version: string;
  harness: string;
  type: string;
  tags: string;
  purpose?: string;
  targetRole?: string;
  authorVerified: string;
  githubStars?: string;
  componentVerified: string;
  supportTier?: string;
  supportState?: string;
  supportEvidence?: string;
  noSupportEvidence?: string;
  yes: string;
  no: string;
  publisher: string;
  publishedAt: string;
  likes: string;
  detailViews?: string;
  artifactDownloads?: string;
  componentKind: string;
  setupKind: string;
  moreActions?: string;
  copyCli?: string;
  copyId?: string;
  copyUrl?: string;
  copied?: string;
  report?: string;
  reportSetup?: string;
  setupsHeading?: string;
  componentsHeading?: string;
  emptySetups?: string;
  emptyComponents?: string;
  pagination?: string;
  setupsPagination?: string;
  componentsPagination?: string;
  whyFailed?: string;
  whyWarning?: string;
  requirements?: string;
  credentialsRequired?: string;
  safetyChecks?: string;
  safetyStatus?: string;
  safetyPercent?: string;
  safetyPassed?: string;
  safetyFailed?: string;
  safetyWarning?: string;
  safetyNotRun?: string;
  safetyIncomplete?: string;
  safetyEmpty?: string;
  safetyNoScan?: string;
  safetyAvailable?: string;
  safetyPending?: string;
  safetyMandatory?: string;
  safetyCheckExplanation?: string;
  like?: string;
  unlike?: string;
  likeMenu?: string;
  unlikeMenu?: string;
};

type CatalogResultsProps = {
  kind: "components" | "setups" | "mixed";
  items: Array<ComponentSummary | SetupSummary>;
  experimental: Array<ComponentSummary | SetupSummary>;
  nextCursor: string | null;
  totalItems?: number | null;
  totalPages?: number | null;
  pageNumber?: number;
  setupsPageNumber?: number;
  componentsPageNumber?: number;
  setupsTotalPages?: number | null;
  componentsTotalPages?: number | null;
  setupsTotalItems?: number | null;
  componentsTotalItems?: number | null;
  view?: "cards" | "list";
  showExperimental: boolean;
  basePath: string;
  query: Record<string, string>;
  labels: CatalogLabels;
  locale?: string;
  authors?: Record<string, CatalogAuthor>;
  likedIds?: ReadonlyArray<string>;
};

function hrefFor(kind: "components" | "setups", stableId: string): string {
  return kind === "components" ? `/catalog/components/${stableId}` : `/catalog/setups/${stableId}`;
}

function objectCardLabels(labels: CatalogLabels): Parameters<typeof ObjectCard>[0]["labels"] {
  return {
    version: labels.version,
    harness: labels.harness,
    type: labels.type,
    tags: labels.tags,
    purpose: labels.purpose,
    targetRole: labels.targetRole,
    authorVerified: labels.authorVerified,
    githubStars: labels.githubStars,
    componentVerified: labels.componentVerified,
    supportTier: labels.supportTier,
    supportState: labels.supportState,
    supportEvidence: labels.supportEvidence,
    noSupportEvidence: labels.noSupportEvidence,
    yes: labels.yes,
    no: labels.no,
    componentKind: labels.componentKind,
    setupKind: labels.setupKind,
    publisher: labels.publisher,
    likes: labels.likes,
    detailViews: labels.detailViews,
    artifactDownloads: labels.artifactDownloads,
    moreActions: labels.moreActions,
    copyCli: labels.copyCli,
    copyId: labels.copyId,
    copyUrl: labels.copyUrl,
    copied: labels.copied,
    report: labels.report,
    reportSetup: labels.reportSetup,
    safetyChecks: labels.safetyChecks,
    safetyStatus: labels.safetyStatus,
    safetyPercent: labels.safetyPercent,
    safetyPassed: labels.safetyPassed,
    safetyFailed: labels.safetyFailed,
    safetyWarning: labels.safetyWarning,
    safetyNotRun: labels.safetyNotRun,
    safetyIncomplete: labels.safetyIncomplete,
    safetyEmpty: labels.safetyEmpty,
    safetyNoScan: labels.safetyNoScan,
    safetyAvailable: labels.safetyAvailable,
    safetyPending: labels.safetyPending,
    safetyMandatory: labels.safetyMandatory,
    whyFailed: labels.whyFailed,
    whyWarning: labels.whyWarning,
    requirements: labels.requirements,
    credentialsRequired: labels.credentialsRequired,
    safetyCheckExplanation: labels.safetyCheckExplanation,
    like: labels.like,
    unlike: labels.unlike,
    likeMenu: labels.likeMenu,
    unlikeMenu: labels.unlikeMenu,
  };
}

function isComponentSummary(item: ComponentSummary | SetupSummary): item is ComponentSummary {
  return "latest_component_type" in item;
}

function mixedCatalogRows({
  visible,
  pageNumber,
  setupsTotalPages,
}: {
  visible: Array<ComponentSummary | SetupSummary>;
  pageNumber: number;
  setupsTotalPages: number | null;
}) {
  const setupRows = visible.filter((item) => !isComponentSummary(item));
  const componentRows = visible.filter(isComponentSummary);
  if (setupsTotalPages === null) return [...setupRows, ...componentRows];
  return pageNumber <= setupsTotalPages ? setupRows : componentRows;
}

export function CatalogResults({
  kind,
  items,
  experimental,
  nextCursor,
  totalItems = null,
  totalPages = null,
  pageNumber = 1,
  setupsTotalPages = null,
  componentsTotalPages = null,
  view = "list",
  showExperimental,
  basePath,
  query,
  labels,
  locale,
  authors = {},
  likedIds = [],
}: CatalogResultsProps) {
  const cardLabels = objectCardLabels(labels);
  const visible = showExperimental ? [...items, ...experimental] : [...items];
  const merged =
    kind === "mixed"
      ? mixedCatalogRows({
          visible,
          pageNumber,
          setupsTotalPages,
        })
      : visible;
  const gridClass =
    view === "list"
      ? "border-border divide-border grid min-w-0 overflow-hidden rounded-lg border divide-y"
      : "grid min-w-0 gap-3 md:grid-cols-2";

  function renderCards(rows: Array<ComponentSummary | SetupSummary>) {
    return (
      <ul className={gridClass}>
        {rows.map((item) => {
          const resource = isComponentSummary(item) ? "components" : "setups";
          return (
            <li key={`${resource}:${item.stable_id}`} className="min-w-0">
              <ObjectCard
                kind={resource === "components" ? "component" : "setup"}
                item={item}
                href={hrefFor(resource, item.stable_id)}
                labels={cardLabels}
                view={view}
                initiallyLiked={likedIds.includes(item.stable_id)}
                {...(authors[item.publisher_id] ? { author: authors[item.publisher_id] } : {})}
                {...(locale ? { locale } : {})}
              />
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <div data-ui={UI.catalog.results} className="flex min-w-0 flex-col gap-8">
      <section aria-labelledby="catalog-results-heading" className="min-w-0" data-resource={kind}>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <div className="min-w-0">
            <h2
              id="catalog-results-heading"
              className="text-xl font-medium tracking-tight break-words"
            >
              {labels.resultsHeading}
            </h2>
            {showExperimental ? (
              <p className="text-muted-foreground mt-1 text-sm leading-relaxed">
                {labels.experimentalNote}
              </p>
            ) : null}
          </div>
          <p className="text-muted-foreground font-mono text-sm" aria-live="polite">
            {totalItems ?? merged.length}
          </p>
        </div>

        {merged.length === 0 ? (
          <StatePanel
            kind="empty"
            title={showExperimental ? labels.emptyAll : labels.emptyAuthoritative}
          />
        ) : (
          renderCards(merged)
        )}
      </section>
      {kind === "mixed" ? null : (
        <SingleResourcePager
          nextCursor={nextCursor}
          totalPages={totalPages}
          pageNumber={pageNumber}
          basePath={basePath}
          query={query}
          nextLabel={labels.nextPage}
          paginationLabel={labels.pagination ?? "Pagination"}
        />
      )}
      {kind === "mixed" ? (
        <MixedPager
          labels={labels}
          pageNumber={pageNumber}
          setupsTotalPages={setupsTotalPages}
          componentsTotalPages={componentsTotalPages}
          basePath={basePath}
          query={query}
        />
      ) : null}
    </div>
  );
}

function MixedPager({
  labels,
  pageNumber,
  setupsTotalPages,
  componentsTotalPages,
  basePath,
  query,
}: Pick<
  CatalogResultsProps,
  "labels" | "pageNumber" | "setupsTotalPages" | "componentsTotalPages" | "basePath" | "query"
>) {
  const setupPages = setupsTotalPages ?? 0;
  const componentPages = componentsTotalPages ?? 0;
  const totalPages = setupPages + componentPages;
  if (totalPages <= 1) return null;
  return (
    <PageNav
      label={labels.pagination ?? "Pagination"}
      pageNumber={pageNumber ?? 1}
      totalPages={totalPages}
      hrefFor={(page) =>
        catalogHref(basePath, {
          ...query,
          page: String(page),
          setups_page: String(page <= setupPages ? page : Math.max(1, setupPages)),
          components_page: String(page <= setupPages ? 1 : page - setupPages),
        })
      }
    />
  );
}
