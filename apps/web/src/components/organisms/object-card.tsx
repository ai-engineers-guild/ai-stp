/* eslint-disable max-lines -- Card, list, and compact metric variants share one fixture. */
import type { ReactNode } from "react";

import { Badge } from "@/components/atoms/badge";
import { CatalogEngagement } from "@/components/molecules/catalog-engagement";
import { CatalogUsageStats } from "@/components/molecules/catalog-usage-stats";
import { CompactChipList } from "@/components/molecules/compact-chip-list";
import { VerifiedAvatar } from "@/components/molecules/verified-avatar";
import { CatalogItemMenu } from "@/components/organisms/catalog-item-menu";
import { VisibilityLabel } from "@/components/molecules/visibility-label";
import type { ComponentSummary, SetupSummary } from "@/lib/api/generated/types.gen";
import type { OwnerObjectSummary } from "@/lib/api/generated/types.gen";
import { namedHarnesses } from "@/lib/catalog-harnesses";
import { cn } from "@/lib/cn";
import { mandatoryFailed, publicationScore } from "@/lib/safety-checks";
import { Link } from "@/lib/i18n/navigation";
import { ownerCatalogItem } from "@/lib/owner-catalog";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme";
import { ComponentTypeIcon } from "@/theme/component-types";

type CatalogItem = ComponentSummary | SetupSummary;
type CardItem = CatalogItem | OwnerObjectSummary;
type Labels = {
  harness: string;
  tags: string;
  likes?: string | undefined;
  githubStars?: string | undefined;
  detailViews?: string | undefined;
  artifactDownloads?: string | undefined;
  componentKind?: string | undefined;
  setupKind?: string | undefined;
  publisher?: string | undefined;
  version?: string | undefined;
  type?: string | undefined;
  authorVerified?: string | undefined;
  authorVerifiedDescription?: string | undefined;
  componentVerified?: string | undefined;
  yes?: string | undefined;
  no?: string | undefined;
  supportTier?: string | undefined;
  supportState?: string | undefined;
  supportEvidence?: string | undefined;
  noSupportEvidence?: string | undefined;
  purpose?: string | undefined;
  targetRole?: string | undefined;
  moreActions?: string | undefined;
  copyCli?: string | undefined;
  copyId?: string | undefined;
  copyUrl?: string | undefined;
  copied?: string | undefined;
  report?: string | undefined;
  reportSetup?: string | undefined;
  safetyNoScan?: string | undefined;
  safetyPercent?: string | undefined;
  safetyStatus?: string | undefined;
  safetyIncomplete?: string | undefined;
  safetyEmpty?: string | undefined;
  safetyPassed?: string | undefined;
  safetyFailed?: string | undefined;
  safetyWarning?: string | undefined;
  safetyNotRun?: string | undefined;
  safetyChecks?: string | undefined;
  safetyAvailable?: string | undefined;
  safetyPending?: string | undefined;
  safetyMandatory?: string | undefined;
  requirements?: string | undefined;
  credentialsRequired?: string | undefined;
  whyFailed?: string | undefined;
  whyWarning?: string | undefined;
  whyOptionalFailed?: string | undefined;
  safetyCheckExplanation?: string | undefined;
  like?: string | undefined;
  unlike?: string | undefined;
  likeMenu?: string | undefined;
  unlikeMenu?: string | undefined;
  assuranceCounts?: string | undefined;
  familyMemberCount?: string | undefined;
  publicVisibility?: string | undefined;
  privateVisibility?: string | undefined;
};
export type CatalogAuthor = { displayName: string | null; avatarUrl: string | null };
const AUTHOR_VERIFIED_FALLBACK = "Author verified";
type Props = {
  kind: "component" | "setup";
  item: CardItem;
  href: string;
  labels: Labels;
  view?: "cards" | "list";
  author?: CatalogAuthor;
  locale?: string | undefined;
  initiallyLiked?: boolean;
  visibility?: "public" | "private";
  ownerActions?: ReactNode;
};

function isOwnerObject(item: CardItem): item is OwnerObjectSummary {
  return "object_kind" in item;
}

function AuthorRail({
  item,
  author,
  labels,
}: {
  item: ComponentSummary | SetupSummary;
  author: CatalogAuthor | undefined;
  labels: Labels;
}) {
  return (
    <div className="flex max-w-full min-w-0 flex-col items-start gap-1 md:max-w-44 md:items-end">
      <Author
        item={item}
        author={author}
        verifiedLabel={verifiedLabel(labels.authorVerifiedDescription)}
      />
    </div>
  );
}

function CatalogMetrics({
  item,
  labels,
  locale,
}: {
  item: ComponentSummary | SetupSummary;
  labels: Labels;
  locale: string;
}) {
  return (
    <div className="relative z-20 flex w-full min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
      <CatalogUsageStats
        metrics={item.usage_metrics}
        locale={locale}
        viewsLabel={labels.detailViews ?? "Detail views"}
        downloadsLabel={labels.artifactDownloads ?? "Artifact downloads"}
        compact
      />
      <CatalogEngagement
        likes={item.likes_count}
        stars={item.github_stars}
        likesLabel={labels.likes}
        starsLabel={labels.githubStars}
      />
    </div>
  );
}

function Author({
  item,
  author,
  verifiedLabel,
}: {
  item: ComponentSummary | SetupSummary;
  author: CatalogAuthor | undefined;
  verifiedLabel: string;
}) {
  return (
    <Link
      href={`/publishers/${item.publisher_id}`}
      prefetch={false}
      className="relative z-10 inline-flex max-w-full min-w-0 items-center gap-2 hover:underline md:max-w-40"
    >
      <VerifiedAvatar
        src={author?.avatarUrl}
        verified={item.latest_trust.author_verified}
        verifiedLabel={verifiedLabel}
        size="sm"
      />
      <span className="truncate text-sm">{author?.displayName?.trim() || item.publisher_id}</span>
    </Link>
  );
}
function MetadataRows({
  type,
  harnesses,
  tags,
  labels,
}: {
  type: string;
  harnesses: readonly string[];
  tags: readonly string[];
  labels: Labels;
}) {
  return (
    <div className="mt-2 min-w-0 space-y-1">
      <div className="flex min-w-0 flex-wrap items-center gap-1">
        <Badge variant="secondary">{type}</Badge>
        <CompactChipList values={harnesses} label={labels.harness} />
      </div>
      <CompactChipList values={tags} label={labels.tags} />
    </div>
  );
}
function TypeMark({
  kind,
  item,
  compact,
}: {
  kind: "component" | "setup";
  item: ComponentSummary | SetupSummary;
  compact: boolean;
}) {
  if (kind === "component")
    return (
      <ComponentTypeIcon
        type={(item as ComponentSummary).latest_component_type}
        compact={compact}
      />
    );
  return (
    <span
      className="bg-muted border-border inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border"
      aria-hidden="true"
    >
      <Icon name="controls" size="sm" />
    </span>
  );
}
function RequirementCount({ item, labels }: { item: CatalogItem; labels: Labels }) {
  return (
    <p className="text-muted-foreground text-xs">
      {labels.requirements ?? "Requirements"}: {item.latest_requirements_count}
      {item.latest_requires_credentials
        ? ` · ${labels.credentialsRequired ?? "credentials required"}`
        : ""}
    </p>
  );
}

function menuLabels(kind: "component" | "setup", labels: Labels) {
  return {
    more: labels.moreActions ?? "More actions",
    copyUrl: labels.copyUrl ?? "Copy URL",
    copyCli: labels.copyCli ?? "Copy CLI command",
    copyId: labels.copyId ?? "Copy ID",
    copied: labels.copied ?? "Copied",
    like: labels.likeMenu ?? labels.like ?? "Like",
    unlike: labels.unlikeMenu ?? "Unlike",
    report:
      kind === "setup"
        ? (labels.reportSetup ?? labels.report ?? "Report setup")
        : (labels.report ?? "Report component"),
  };
}

/** Sparse catalog item: identity, compatibility, tags, author and likes only. */
// eslint-disable-next-line max-lines-per-function
export function ObjectCard({
  kind,
  item,
  href,
  labels,
  view = "list",
  author,
  locale = "en",
  initiallyLiked = false,
  visibility = "public",
  ownerActions,
}: Props) {
  const owner = isOwnerObject(item) ? item : null;
  const catalogItem: CatalogItem | null = isOwnerObject(item) ? ownerCatalogItem(item) : item;
  if (!catalogItem) {
    if (!owner) return null;
    return (
      <OwnerFallbackCard
        item={owner}
        href={href}
        actions={ownerActions}
        publicLabel={labels.publicVisibility}
        privateLabel={labels.privateVisibility}
      />
    );
  }
  const itemVisibility = owner?.visibility ?? visibility;
  const type =
    kind === "component"
      ? (catalogItem as ComponentSummary).latest_component_type
      : (labels.setupKind ?? "Setup");
  const harnesses = namedHarnesses(catalogItem);
  const actions = menuLabels(kind, labels);
  const authorBlock = <AuthorRail item={catalogItem} author={author} labels={labels} />;
  const metrics = <CatalogMetrics item={catalogItem} labels={labels} locale={locale} />;
  const reason = whyOpen(catalogItem, labels, view);
  if (view === "list")
    return (
      <article
        data-ui={UI.catalog.card}
        className={cn(
          "group relative min-w-0 overflow-x-hidden px-4 py-3 transition-colors",
          kind === "setup"
            ? "bg-muted/50 hover:bg-muted"
            : "bg-background hover:bg-muted/35 focus-within:bg-muted/35",
        )}
        data-kind={kind}
        data-view="list"
      >
        <div className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-x-3 gap-y-3 md:grid-cols-[auto_minmax(0,1fr)_auto_minmax(8rem,11rem)_minmax(8rem,auto)_auto] md:items-center">
          <div className="shrink-0">
            <TypeMark kind={kind} item={catalogItem} compact />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="min-w-0 text-base leading-snug font-medium break-words">
              <Link
                href={href}
                prefetch={false}
                className="after:absolute after:inset-0 focus-visible:outline-none"
              >
                {catalogItem.latest_name}
              </Link>
            </h3>
            {reason ? (
              <p className="text-muted-foreground mt-1 line-clamp-1 text-xs" data-why-open="">
                {reason}
              </p>
            ) : null}
            <MetadataRows
              type={type}
              harnesses={harnesses}
              tags={catalogItem.latest_tags}
              labels={labels}
            />
            <CardFacts item={catalogItem} kind={kind} labels={labels} />
          </div>
          <div className="relative z-20 col-start-3 row-start-1 flex items-center gap-2 md:col-start-6">
            {owner ? ownerActions : null}
            {!owner ? (
              <CatalogItemMenu
                kind={kind}
                stableId={catalogItem.stable_id}
                version={catalogItem.latest_version}
                href={href}
                initiallyLiked={initiallyLiked}
                labels={actions}
              />
            ) : null}
          </div>
          <div className="col-start-2 row-start-2 min-w-0 md:col-start-3 md:row-start-1 md:justify-self-end">
            {metrics}
          </div>
          <div className="col-start-2 row-start-3 min-w-0 md:col-start-4 md:row-start-1">
            {kind === "component" ? (
              <SafetyScore item={catalogItem} labels={labels} compact />
            ) : null}
          </div>
          <div className="relative z-20 col-span-2 col-start-2 row-start-4 min-w-0 md:col-span-1 md:col-start-5 md:row-start-1 md:justify-self-end">
            {authorBlock}
          </div>
        </div>
        <VisibilityLabel
          className="absolute top-0 right-4 z-20"
          visibility={itemVisibility}
          publicLabel={labels.publicVisibility}
          privateLabel={labels.privateVisibility}
        />
      </article>
    );
  return (
    <article
      data-ui={UI.catalog.card}
      className={cn(
        "group border-border focus-within:ring-ring relative flex h-full min-w-0 flex-col gap-3 overflow-x-hidden rounded-lg border p-3 shadow-sm transition-colors focus-within:ring-2",
        kind === "setup" ? "bg-muted/50 hover:bg-muted p-4" : "bg-card hover:bg-muted/30",
      )}
      data-kind={kind}
      data-view="cards"
    >
      <div className="flex items-start gap-3">
        <TypeMark kind={kind} item={catalogItem} compact />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-start gap-2">
            <h3 className="min-w-0 flex-1 text-lg leading-snug font-medium">
              <Link
                href={href}
                prefetch={false}
                className="after:absolute after:inset-0 focus-visible:outline-none"
              >
                {catalogItem.latest_name}
              </Link>
            </h3>
            <div className="relative z-20 flex shrink-0 items-center gap-2">
              {owner ? ownerActions : null}
              {!owner ? (
                <CatalogItemMenu
                  kind={kind}
                  stableId={catalogItem.stable_id}
                  version={catalogItem.latest_version}
                  href={href}
                  initiallyLiked={initiallyLiked}
                  labels={actions}
                />
              ) : null}
            </div>
          </div>
          <MetadataRows
            type={type}
            harnesses={harnesses}
            tags={catalogItem.latest_tags}
            labels={labels}
          />
          <CardFacts item={catalogItem} kind={kind} labels={labels} />
          {reason ? (
            <p className="text-muted-foreground mt-1 line-clamp-1 text-xs" data-why-open="">
              {reason}
            </p>
          ) : null}
        </div>
      </div>
      <p className="text-muted-foreground line-clamp-2 text-sm leading-relaxed">
        {catalogItem.latest_description}
      </p>
      <div className="flex flex-wrap items-center justify-between gap-3 py-1">
        {metrics}
        {kind === "component" ? <SafetyScore item={catalogItem} labels={labels} /> : null}
      </div>
      <div className="border-border relative z-20 mt-auto flex items-end justify-between gap-3 border-t pt-3">
        <RequirementCount item={catalogItem} labels={labels} />
        {authorBlock}
      </div>
      <VisibilityLabel
        className="absolute top-0 right-4 z-20"
        visibility={itemVisibility}
        publicLabel={labels.publicVisibility}
        privateLabel={labels.privateVisibility}
      />
    </article>
  );
}

export function OwnerObjectCard({
  item,
  href,
  actions,
  publicLabel = "public",
  privateLabel = "private",
  authorVerifiedLabel,
  componentVerifiedLabel,
}: {
  item: OwnerObjectSummary;
  href: string;
  actions: ReactNode;
  publicLabel?: string | undefined;
  privateLabel?: string | undefined;
  authorVerifiedLabel: string;
  componentVerifiedLabel: string;
}) {
  void authorVerifiedLabel;
  void componentVerifiedLabel;
  return (
    <ObjectCard
      kind={item.object_kind}
      item={item}
      href={href}
      labels={{
        harness: "",
        tags: "",
        publicVisibility: publicLabel,
        privateVisibility: privateLabel,
      }}
      ownerActions={actions}
    />
  );
}

function OwnerFallbackCard({
  item,
  href,
  actions,
  publicLabel,
  privateLabel,
}: {
  item: OwnerObjectSummary;
  href: string;
  actions: ReactNode;
  publicLabel?: string | undefined;
  privateLabel?: string | undefined;
}) {
  return (
    <article
      data-ui={UI.catalog.card}
      data-kind={item.object_kind}
      data-view="cards"
      className="bg-card group border-border hover:bg-muted/30 relative flex h-full min-w-0 flex-col gap-3 overflow-x-hidden rounded-lg border p-4 shadow-sm transition-colors"
    >
      <div className="flex min-w-0 items-start gap-3 pr-16">
        <span
          className="bg-muted border-border text-foreground inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border"
          aria-hidden="true"
        >
          <Icon name="controls" size="sm" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-muted-foreground font-mono text-xs tracking-wide uppercase">
            {item.object_kind}
          </p>
          <h2 className="mt-1 min-w-0 text-lg leading-snug font-medium">
            <Link
              href={href}
              prefetch={false}
              className="after:absolute after:inset-0 focus-visible:outline-none"
            >
              {item.name}
            </Link>
          </h2>
          <p className="text-muted-foreground mt-1 font-mono text-xs break-all">{item.stable_id}</p>
        </div>
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {item.latest_version ? (
          <span className="font-mono text-xs">{item.latest_version}</span>
        ) : null}
      </div>
      <div className="relative z-20">{actions}</div>
      <VisibilityLabel
        className="absolute top-0 right-4 z-20"
        visibility={item.visibility}
        publicLabel={publicLabel}
        privateLabel={privateLabel}
      />
    </article>
  );
}

function isComponentSummary(item: CatalogItem): item is ComponentSummary {
  return "latest_component_type" in item;
}

function isSetupSummary(item: CatalogItem): item is SetupSummary {
  return "family_member_count" in item;
}

export function formatAssuranceCounts(verified: number, assessed: number, label: string): string {
  if (assessed <= 0) {
    return `${label}: 0 / 0`;
  }
  return `${label}: ${verified} / ${assessed} (${Math.round((verified / assessed) * 100)}%)`;
}

function CardFacts({
  item,
  kind,
  labels,
}: {
  item: CatalogItem;
  kind: "component" | "setup";
  labels: Labels;
}) {
  const assurance = isComponentSummary(item)
    ? item.latest_assurance
    : { verified_targets: 0, assessed_targets: 0 };
  return (
    <div className="text-muted-foreground mt-1 flex min-w-0 flex-wrap gap-x-3 gap-y-1 text-xs">
      {kind === "component" && isComponentSummary(item) ? (
        <p data-ui={UI.catalog.assurance}>
          {formatAssuranceCounts(
            assurance.verified_targets,
            assurance.assessed_targets,
            labels.assuranceCounts ?? "Verified targets",
          )}
        </p>
      ) : null}
      {kind === "setup" && isSetupSummary(item) && item.family_member_count ? (
        <p>
          {labels.familyMemberCount ?? "Family members"}: {item.family_member_count}
        </p>
      ) : null}
    </div>
  );
}

function whyOpen(item: CatalogItem, labels: Labels, view: "cards" | "list"): string | null {
  const summary = item.latest_checks;
  if (summary && summary.failed > 0) {
    const gateFailed =
      mandatoryFailed(summary.checks) ||
      (summary.checks.length === 0 && !item.latest_trust.component_verified);
    if (gateFailed) {
      return labels.whyFailed ?? `${summary.failed} failed checks`;
    }
    return labels.whyOptionalFailed ?? labels.whyWarning ?? `${summary.failed} optional findings`;
  }
  if (summary && summary.warning > 0) {
    return labels.whyWarning ?? `${summary.warning} warnings`;
  }
  if (item.latest_requires_credentials) {
    return labels.credentialsRequired ?? "credentials required";
  }
  if (view === "cards") return null;
  const description = item.latest_description.trim();
  return description || null;
}

function verifiedLabel(value: string | undefined): string {
  return value || `${AUTHOR_VERIFIED_FALLBACK}; this does not indicate content safety`;
}

function SafetyScore({
  item,
  labels,
  compact = false,
}: {
  item: ComponentSummary | SetupSummary;
  labels: Labels;
  compact?: boolean;
}) {
  const summary = item.latest_checks;
  const explanation =
    labels.safetyCheckExplanation ??
    "Publication checks: automated checks required before this component version can be published.";
  const computed = summary && summary.status !== "empty" ? publicationScore(summary) : null;
  if (computed === null || !summary) {
    return (
      <p
        className="text-muted-foreground text-center text-xs"
        title={labels.safetyNoScan ?? explanation}
        data-safety="empty"
      >
        {labels.safetyNoScan ?? "No checks yet"}
      </p>
    );
  }
  const score = Math.max(0, Math.min(100, computed));
  const accessibleName = `${explanation} ${score}%`;
  return (
    <div
      className="flex min-w-0 items-center gap-1.5"
      title={explanation}
      data-safety={summary.status}
      role="meter"
      aria-label={accessibleName}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={score}
    >
      <span
        className={cn(
          "bg-muted relative block h-1 overflow-hidden rounded-full",
          compact ? "w-8" : "w-10",
        )}
        aria-hidden="true"
      >
        <span
          data-safety-fill=""
          className="absolute inset-y-0 left-0 overflow-hidden"
          style={{ width: `${score}%` }}
        >
          <span
            className={cn("block h-full", compact ? "w-8" : "w-10")}
            style={{
              background:
                "linear-gradient(90deg, hsl(var(--destructive)), hsl(var(--warning)), hsl(var(--success)))",
            }}
          />
        </span>
      </span>
      <span className="font-mono text-sm font-medium tabular-nums">{score}%</span>
    </div>
  );
}
