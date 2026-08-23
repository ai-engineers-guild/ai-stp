import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { ObjectAuthorRail } from "@/components/molecules/catalog-author-link";
import { CatalogUsageStats } from "@/components/molecules/catalog-usage-stats";
import { CliCopyBlock } from "@/components/molecules/cli-copy-block";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { MarkdownDescription } from "@/components/molecules/markdown-description";
import { ObjectRelationships } from "@/components/molecules/object-relationships";
import { ObjectTechnicalDetails } from "@/components/molecules/object-technical-details";
import { ObjectVersionHistory } from "@/components/molecules/object-version-history";
import { OsBadgeList } from "@/components/molecules/os-badge-list";
import { PassportJsonViewer } from "@/components/molecules/passport-json-viewer";
import {
  requirementLabels,
  RequirementsSummary,
} from "@/components/molecules/requirements-summary";
import {
  SafetyChecksSummaryView,
  safetyChecksLabels,
} from "@/components/molecules/safety-checks-summary";
import { StatePanel } from "@/components/molecules/state-panel";
import { ComponentMediaGallery } from "@/components/organisms/component-media-gallery";
import { ObjectDetailFrame } from "@/components/organisms/object-detail-frame";
import { ObjectDetailHeader } from "@/components/organisms/object-detail-header";
import {
  catalogRelations,
  readComponent,
  readComponentGithubMetadata,
  readComponentVersion,
} from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/errors";
import { readOwnerObject } from "@/lib/api/owner";
import { listCatalogReactions } from "@/lib/api/reactions";
import { readPublisherProfile } from "@/lib/api/public-profile";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { asAccountId, asVersionId, tryAsComponentId } from "@/lib/brands";
import { namedHarnesses, namedOperatingSystems } from "@/lib/catalog-harnesses";
import { registryVersion } from "@/lib/cli-copy";
import { buildDeepLink, normalizeTarget } from "@/lib/deep-links";
import { publicOrigin } from "@/lib/site";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";
import { ComponentTypeIcon } from "@/theme/component-types";
import { Icon } from "@/theme/icons";

type PageProps = { params: Promise<{ locale: string; stableId: string }> };

// Page owns both human layout and machine presenter branch from the same reads.
// eslint-disable-next-line max-lines-per-function, complexity
export default async function ComponentDetailPage({ params }: PageProps) {
  const { locale, stableId } = await params;
  setRequestLocale(locale);
  const componentId = tryAsComponentId(stableId);
  if (!componentId) notFound();

  let detail;
  try {
    detail = await readComponent(componentId);
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_NOT_FOUND") notFound();
    const tc = await getTranslations("common");
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  const t = await getTranslations("catalog");
  const to = await getTranslations("objects");
  const tc = await getTranslations("common");
  const tCli = await getTranslations("cli");

  const summary = detail.summary;
  const latest = await readLatestComponentVersion(stableId, summary.latest_version);
  const passport = latest?.passport;
  const ownerId = passport?.owner_id || summary.publisher_id;
  const author = await readAuthor(ownerId);
  const token = await sessionCookieValue();
  const isOwner = token ? await canEditComponent(token, stableId) : false;
  const initiallyLiked = token ? await isLiked(token, "component", stableId) : false;
  const metadata = await readComponentGithubMetadata(
    componentId,
    asVersionId(summary.latest_version),
  ).catch(() => ({ schema_version: 1 as const, stars: null, archived: null }));
  const reportHref = latest?.passport_digest
    ? `/${locale}/reports?object_kind=component&stable_id=${encodeURIComponent(stableId)}&version=${encodeURIComponent(summary.latest_version)}&digest=${encodeURIComponent(latest.passport_digest)}`
    : undefined;
  const relations = catalogRelations(detail);
  const media = detail.media;
  const cliCommand = registryVersion("component", summary.stable_id, summary.latest_version);
  const canonical = buildDeepLink(
    publicOrigin().origin,
    normalizeTarget({
      kind: "component",
      stable_id: summary.stable_id,
      locale: locale === "en" ? "en" : "ru",
    }),
  );

  return (
    <article className="mx-auto max-w-6xl min-w-0 space-y-8 overflow-x-clip">
      <Button asChild variant="ghost" size="sm">
        <Link href="/catalog?include_experimental=1&resource=components">
          <Icon name="arrowLeft" size="sm" /> {t("backToCatalog")}
        </Link>
      </Button>

      <ObjectDetailHeader
        icon={<ComponentTypeIcon type={summary.latest_component_type} />}
        title={summary.latest_name}
        badges={
          <>
            <Badge variant="secondary">{summary.latest_component_type}</Badge>
            {namedHarnesses(summary).map((harness) => (
              <Badge key={harness} variant="outline">
                {harness}
              </Badge>
            ))}
          </>
        }
        versionLabel={`v${summary.latest_version}`}
        githubStars={metadata.stars}
        githubStarsLabel={t("githubStars")}
        archived={metadata.archived}
        archivedLabel={t("githubArchived")}
        source={passport?.source}
        viewSourceLabel={t("viewSourceOnGithub")}
        like={{
          stableId,
          objectKind: "component",
          sharePath: `/${locale}/catalog/components/${stableId}/versions/${summary.latest_version}`,
          likesCount: summary.likes_count,
          initiallyLiked,
          reportHref,
          ...(isOwner ? { editHref: `/objects/component/${stableId}/edit` } : {}),
          cliCommand,
          canonicalUrl: canonical.web_url,
          labels: {
            copyUrl: t("copyUrl"),
            share: t("share"),
            copyId: t("copyId"),
            copyCli: t("copyCli"),
            copied: t("copied"),
            like: t("like"),
            unlike: t("unlike"),
            likeMenu: t("likeMenu"),
            unlikeMenu: t("unlikeMenu"),
            more: t("moreActions"),
            report: t("report"),
            editPresentation: to("editPresentation"),
          },
        }}
      />

      <ObjectRelationships
        countryCodes={relations.country_codes}
        services={relations.services}
        locale={locale}
        labels={{
          localization: t("localization"),
          linkedServices: t("linkedServices"),
          notExclusive: t("servicesNotExclusive"),
        }}
      />

      <ObjectDetailFrame
        description={
          <MarkdownDescription
            source={passport?.description ?? summary.latest_description}
            heading={t("description")}
          />
        }
        media={
          media.length > 0 ? (
            <ComponentMediaGallery
              items={media}
              labels={{
                gallery: t("gallery"),
                open: t("openMedia"),
                source: t("mediaSource"),
                close: t("closeMedia"),
                previous: t("previousMedia"),
                next: t("nextMedia"),
              }}
            />
          ) : undefined
        }
        main={
          <>
            {passport ? (
              <ObjectTechnicalDetails
                title={t("technicalDetails")}
                summary={summary.latest_lifecycle}
                facts={[
                  { label: t("lifecycle"), value: summary.latest_lifecycle },
                  { label: t("projectionKind"), value: summary.latest_projection_kind },
                  {
                    label: t("requiresCredentials"),
                    value: passport.requires_credentials ? tc("yes") : tc("no"),
                  },
                  { label: t("requiresAuthorization"), value: passport.requires_authorization },
                  { label: t("publishedAt"), value: summary.latest_published_at },
                  { label: t("harness"), value: namedHarnesses(summary).join(", ") },
                ]}
                licenseId={passport.license.spdx_id}
                licenseLabel={t("license")}
              />
            ) : null}
            {passport ? (
              <RequirementsSummary requirements={passport} labels={requirementLabels(t, tc)} />
            ) : null}
            <SafetyChecksSummaryView
              summary={summary.latest_checks}
              labels={safetyChecksLabels(t)}
            />
            {passport ? <ComponentCompatibility passport={passport} t={t} /> : null}
          </>
        }
        rail={
          <>
            <ObjectAuthorRail
              accountId={ownerId}
              displayName={author?.display_name}
              avatarUrl={author?.avatar_url}
              verified={summary.latest_trust.author_verified}
              verifiedLabel={t("authorVerified")}
              authorLabel={t("author")}
            />
            <div className="border-border bg-card rounded-lg border p-4 shadow-sm">
              <CatalogUsageStats
                metrics={summary.usage_metrics}
                locale={locale}
                viewsLabel={t("detailViews")}
                downloadsLabel={t("artifactDownloads")}
              />
            </div>
            <CliCopyBlock
              command={cliCommand}
              title={tCli("useTitle")}
              description={tCli("useBody")}
              copyLabel={tCli("copy")}
              copiedLabel={tCli("copied")}
              errorLabel={tCli("copyError")}
              docsLabel={tCli("docs")}
            />
            <ObjectVersionHistory
              title={t("versionHistory")}
              note={t("versionGapNote")}
              currentLabel={t("currentVersion")}
              emptyLabel={t("noVersions")}
              hrefFor={(version) => `/catalog/components/${stableId}/versions/${version}`}
              versions={detail.versions}
              current={summary.latest_version}
            />
          </>
        }
        passport={
          passport ? (
            <DetailAccordion title={t("passport")} summary={t("passportHint")}>
              <div data-ui={UI.component.passport}>
                <PassportJsonViewer
                  value={passport}
                  label={t("passportReadable")}
                  copyLabel={t("copyPassport")}
                  copiedLabel={t("copied")}
                  errorLabel={tCli("copyError")}
                />
              </div>
            </DetailAccordion>
          ) : undefined
        }
      />
    </article>
  );
}

async function readLatestComponentVersion(stableId: string, version: string) {
  const componentId = tryAsComponentId(stableId);
  if (!componentId) return null;
  try {
    return await readComponentVersion(componentId, asVersionId(version));
  } catch {
    return null;
  }
}

async function readAuthor(accountId: string) {
  try {
    return await readPublisherProfile(asAccountId(accountId));
  } catch {
    return null;
  }
}

async function canEditComponent(token: string, stableId: string) {
  try {
    await readOwnerObject(token, "component", stableId);
    return true;
  } catch {
    return false;
  }
}

async function isLiked(token: string, objectKind: "component" | "setup", stableId: string) {
  try {
    const reactions = await listCatalogReactions(token);
    return reactions.items.some(
      (item) => item.object_kind === objectKind && item.summary.stable_id === stableId,
    );
  } catch {
    return false;
  }
}

function ComponentCompatibility({
  passport,
  t,
}: {
  passport: NonNullable<Awaited<ReturnType<typeof readComponentVersion>>["passport"]>;
  t: (key: string) => string;
}) {
  const osValues = namedOperatingSystems(passport);
  const evidence = passport.compatibility_evidence_refs.join(", ") || t("noEvidence");
  return (
    <DetailAccordion title={t("compatibility")}>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div className="bg-muted/30 min-w-0 rounded-sm p-3">
          <dt className="text-muted-foreground text-sm">{t("supportedOs")}</dt>
          <dd className="mt-1 font-medium break-words">
            <OsBadgeList values={osValues} empty={t("noneListed")} />
          </dd>
        </div>
        <div className="bg-muted/30 min-w-0 rounded-sm p-3">
          <dt className="text-muted-foreground text-sm">{t("evidenceSummary")}</dt>
          <dd className="mt-1 font-medium break-words">{evidence}</dd>
        </div>
      </dl>
    </DetailAccordion>
  );
}
