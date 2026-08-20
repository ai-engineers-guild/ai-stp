import { Badge } from "@/components/atoms/badge";
import { CatalogEngagement } from "@/components/molecules/catalog-engagement";
import { CatalogUsageStats } from "@/components/molecules/catalog-usage-stats";
import { VerifiedAvatar } from "@/components/molecules/verified-avatar";
import { CatalogItemMenu } from "@/components/organisms/catalog-item-menu";
import type { ComponentSummary, SetupSummary } from "@/lib/api/generated/types.gen";
import { cn } from "@/lib/cn";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme";
import { ComponentTypeIcon } from "@/theme/component-types";

type CatalogItem = ComponentSummary | SetupSummary;
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
};
export type CatalogAuthor = { displayName: string | null; avatarUrl: string | null };
const AUTHOR_VERIFIED_FALLBACK = "Author verified";
type Props = {
  kind: "component" | "setup";
  item: CatalogItem;
  href: string;
  labels: Labels;
  view?: "cards" | "list";
  author?: CatalogAuthor;
  locale?: string;
};
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
        label={labels.publisher ?? "Publisher"}
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
  label,
  verifiedLabel,
}: {
  item: ComponentSummary | SetupSummary;
  author: CatalogAuthor | undefined;
  label: string;
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
      <span className="truncate text-sm">{author?.displayName?.trim() || label}</span>
    </Link>
  );
}
function Harnesses({ values, label }: { values: string[]; label: string }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1" aria-label={label}>
      {values.map((value) => (
        <Badge key={value} variant="secondary">
          {value}
        </Badge>
      ))}
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
  compact?: boolean;
}) {
  if (kind === "component")
    return (
      <ComponentTypeIcon
        type={(item as ComponentSummary).latest_component_type}
        {...(compact === undefined ? {} : { compact })}
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
    report:
      kind === "setup"
        ? (labels.reportSetup ?? labels.report ?? "Report setup")
        : (labels.report ?? "Report component"),
  };
}

/** Sparse catalog item: identity, compatibility, tags, author and likes only. */
export function ObjectCard({
  kind,
  item,
  href,
  labels,
  view = "list",
  author,
  locale = "en",
}: Props) {
  const type =
    kind === "component"
      ? (item as ComponentSummary).latest_component_type
      : (labels.setupKind ?? "Setup");
  const harnesses = [item.latest_harness_id];
  const actions = menuLabels(kind, labels);
  const authorBlock = <AuthorRail item={item} author={author} labels={labels} />;
  const metrics = <CatalogMetrics item={item} labels={labels} locale={locale} />;
  const reason = whyOpen(item, labels, view);
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
            <TypeMark kind={kind} item={item} compact />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="min-w-0 text-base leading-snug font-medium break-words">
              <Link
                href={href}
                prefetch={false}
                className="after:absolute after:inset-0 focus-visible:outline-none"
              >
                {item.latest_name}
              </Link>
            </h3>
            {reason ? (
              <p className="text-muted-foreground mt-1 line-clamp-1 text-xs" data-why-open="">
                {reason}
              </p>
            ) : null}
            <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
              <Badge variant="outline">{type}</Badge>
              <Harnesses values={harnesses} label={labels.harness} />
              <div className="flex min-w-0 flex-wrap gap-1">
                {item.latest_tags.slice(0, 2).map((tag) => (
                  <Badge key={tag} variant="outline">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
          <div className="relative z-20 col-start-3 row-start-1 md:col-start-6">
            <CatalogItemMenu
              kind={kind}
              stableId={item.stable_id}
              version={item.latest_version}
              href={href}
              labels={actions}
            />
          </div>
          <div className="col-start-2 row-start-2 min-w-0 md:col-start-3 md:row-start-1 md:justify-self-end">
            {metrics}
          </div>
          <div className="col-start-2 row-start-3 min-w-0 md:col-start-4 md:row-start-1">
            <SafetyScore item={item} labels={labels} compact />
          </div>
          <div className="relative z-20 col-span-2 col-start-2 row-start-4 min-w-0 md:col-span-1 md:col-start-5 md:row-start-1 md:justify-self-end">
            {authorBlock}
          </div>
        </div>
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
        <TypeMark kind={kind} item={item} compact />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-start gap-2">
            <h3 className="min-w-0 flex-1 text-lg leading-snug font-medium">
              <Link
                href={href}
                prefetch={false}
                className="after:absolute after:inset-0 focus-visible:outline-none"
              >
                {item.latest_name}
              </Link>
            </h3>
            <div className="relative z-20 shrink-0">
              <CatalogItemMenu
                kind={kind}
                stableId={item.stable_id}
                version={item.latest_version}
                href={href}
                labels={actions}
              />
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1">
            <Badge variant="secondary">{type}</Badge>
            <Harnesses values={harnesses} label={labels.harness} />
          </div>
          {reason ? (
            <p className="text-muted-foreground mt-1 line-clamp-1 text-xs" data-why-open="">
              {reason}
            </p>
          ) : null}
        </div>
      </div>
      <p className="text-muted-foreground line-clamp-2 text-sm leading-relaxed">
        {item.latest_description}
      </p>
      <div className="flex flex-wrap items-center justify-between gap-3 py-1">
        {metrics}
        <SafetyScore item={item} labels={labels} />
      </div>
      <div className="flex flex-wrap gap-1">
        {item.latest_tags.map((tag) => (
          <Badge key={tag} variant="outline">
            {tag}
          </Badge>
        ))}
      </div>
      <div className="border-border relative z-20 mt-auto flex items-end justify-between gap-3 border-t pt-3">
        <RequirementCount item={item} labels={labels} />
        {authorBlock}
      </div>
    </article>
  );
}

function whyOpen(item: CatalogItem, labels: Labels, view: "cards" | "list"): string | null {
  const summary = item.latest_checks;
  if (summary && summary.failed > 0) {
    return labels.whyFailed ?? `${summary.failed} failed checks`;
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
  const title = labels.safetyChecks ?? "Safety checks";
  if (!summary || summary.status === "empty" || summary.total_countable === 0) {
    return (
      <p
        className="text-muted-foreground text-center text-xs"
        title={labels.safetyNoScan ?? title}
        data-safety="empty"
      >
        {labels.safetyNoScan ?? "No checks yet"}
      </p>
    );
  }
  const percent = summary.checks_passed_percent;
  const derivedPercent = summary.checks.length
    ? Math.round((100 * summary.passed) / summary.checks.length)
    : 0;
  const score = Math.max(0, Math.min(100, typeof percent === "number" ? percent : derivedPercent));
  return (
    <div
      className={cn(
        "flex w-full min-w-0 items-center gap-2",
        compact ? "max-w-full md:max-w-40" : "max-w-full md:max-w-52",
      )}
      title={`${title}: ${score}% (${summary.passed}/${summary.checks.length})`}
      data-safety={summary.status}
      role="meter"
      aria-label={`${title}: ${score}%`}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={score}
    >
      <span className="bg-muted relative block h-2 flex-1 rounded-full" aria-hidden="true">
        <span
          className="absolute inset-0 rounded-full"
          style={{
            background:
              "linear-gradient(90deg, var(--destructive), var(--warning), var(--success))",
          }}
        />
        <span
          className="bg-muted absolute inset-y-0 right-0 rounded-r-full"
          style={{ width: `${100 - score}%` }}
        />
        <span
          className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
          style={{
            left: `${score}%`,
            background: `color-mix(in srgb, var(--destructive) ${100 - score}%, var(--success) ${score}%)`,
            boxShadow: `0 0 10px color-mix(in srgb, color-mix(in srgb, var(--destructive) ${100 - score}%, var(--success) ${score}%) 65%, transparent)`,
          }}
        />
      </span>
      <span className="min-w-10 text-right font-mono text-sm font-medium tabular-nums">
        {score}%
      </span>
    </div>
  );
}
