import type { Metadata } from "next";
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
import { PassportJsonViewer } from "@/components/molecules/passport-json-viewer";
import {
  mergeRequirements,
  requirementLabels,
  RequirementsSummary,
} from "@/components/molecules/requirements-summary";
import { StatePanel } from "@/components/molecules/state-panel";
import { contextBudgetLabels } from "@/components/organisms/context-budget-labels";
import { ContextBudgetPanel } from "@/components/organisms/context-budget-panel";
import { ObjectDetailFrame } from "@/components/organisms/object-detail-frame";
import { ObjectDetailHeader } from "@/components/organisms/object-detail-header";
import { SetupComposition } from "@/components/organisms/setup-composition";
import {
  catalogRelations,
  readComponentVersion,
  readSetup,
  readSetupContextBudget,
  readSetupGithubMetadata,
  readSetupVersion,
} from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/errors";
import { listCatalogReactions } from "@/lib/api/reactions";
import { readPublisherProfile, type PublicProfileProjection } from "@/lib/api/public-profile";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { asAccountId, asComponentId, asVersionId, tryAsSetupId } from "@/lib/brands";
import { namedHarnesses } from "@/lib/catalog-harnesses";
import { registryVersion, selectImpact } from "@/lib/cli-copy";
import { buildDeepLink, normalizeTarget } from "@/lib/deep-links";
import { publicOrigin } from "@/lib/site";
import { Link } from "@/lib/i18n/navigation";
import { SeoJsonLd } from "@/components/molecules/seo-json-ld";
import { readSeoProfile } from "@/lib/api/seo";
import { metadataFromSeo } from "@/lib/seo/metadata";
import { UI } from "@/lib/ui-selectors";
import { sourceLinksFor } from "@/lib/source-url";
import { Icon } from "@/theme/icons";

type PageProps = { params: Promise<{ locale: string; stableId: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale, stableId } = await params;
  const seo = await readSeoProfile("setup", stableId, locale);
  return metadataFromSeo(seo, { title: stableId });
}

// Page owns both human layout and machine presenter branch from the same reads.

// The server page intentionally keeps its reads and matching render states together.
// eslint-disable-next-line complexity, max-lines-per-function
export default async function SetupDetailPage({ params }: PageProps) {
  const { locale, stableId } = await params;
  setRequestLocale(locale);
  const setupId = tryAsSetupId(stableId);
  if (!setupId) notFound();

  let detail;
  try {
    detail = await readSetup(setupId);
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_NOT_FOUND") notFound();
    const tc = await getTranslations("common");
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  const t = await getTranslations("catalog");
  const tc = await getTranslations("common");
  const tCli = await getTranslations("cli");
  const reportLabel = t("reportSetup");

  const seo = await readSeoProfile("setup", stableId, locale);
  const summary = detail.summary;
  const token = await sessionCookieValue();
  const initiallyLiked = token ? await isLiked(token, stableId) : false;
  let latest: Awaited<ReturnType<typeof readSetupVersion>> | null = null;
  try {
    latest = await readSetupVersion(setupId, asVersionId(summary.latest_version));
  } catch {
    latest = null;
  }
  const passport = latest?.passport;
  const catalogComponents = passport
    ? await Promise.all(
        passport.components.map(async (ref) => {
          try {
            const component = await readComponentVersion(
              asComponentId(ref.stable_id),
              asVersionId(ref.version),
            );
            const componentAuthor = await readAuthor(component.passport.owner_id);
            return {
              stableId: ref.stable_id,
              version: ref.version,
              componentType: component.passport.component_type,
              ownerId: component.passport.owner_id,
              authorName: componentAuthor?.display_name,
              sourceUrl: sourceLinksFor(component.passport.source, component.passport.facts)[0]
                ?.href,
              passport: component.passport,
            };
          } catch {
            return null;
          }
        }),
      ).then((items) => items.filter((item) => item !== null))
    : [];
  const aggregatedRequirements = passport
    ? mergeRequirements([passport, ...catalogComponents.map((item) => item.passport)])
    : null;
  const ownerId = passport?.owner_id || summary.publisher_id;
  const author = await readAuthor(ownerId);
  const reportHref = latest?.passport_digest
    ? `/${locale}/reports?object_kind=setup&stable_id=${encodeURIComponent(stableId)}&version=${encodeURIComponent(summary.latest_version)}&digest=${encodeURIComponent(latest.passport_digest)}`
    : undefined;
  const relations = catalogRelations(detail);
  const metadata = await readSetupGithubMetadata(
    setupId,
    asVersionId(summary.latest_version),
  ).catch(() => ({ schema_version: 1 as const, stars: null, archived: null }));
  const budget = await readSetupContextBudget(setupId, asVersionId(summary.latest_version)).catch(
    () => null,
  );
  const cliCommand = registryVersion("setup", summary.stable_id, summary.latest_version);
  const impactCommand = selectImpact(summary.stable_id, summary.latest_version);
  const canonical = buildDeepLink(
    publicOrigin().origin,
    normalizeTarget({
      kind: "setup",
      stable_id: summary.stable_id,
      locale: locale === "en" ? "en" : "ru",
    }),
  );

  return (
    <article className="mx-auto max-w-6xl min-w-0 space-y-8 overflow-x-clip">
      {seo ? <SeoJsonLd jsonLd={seo.profile.json_ld} /> : null}
      <Button asChild variant="ghost" size="sm">
        <Link href="/catalog?include_experimental=1&resource=setups">
          <Icon name="arrowLeft" size="sm" /> {t("backToCatalog")}
        </Link>
      </Button>

      <ObjectDetailHeader
        icon={
          <img
            src="/catalog-art/setup.webp"
            alt=""
            className="bg-muted h-12 w-12 shrink-0 rounded-lg object-cover sm:h-16 sm:w-16"
          />
        }
        title={summary.latest_name}
        badges={
          <>
            <Badge variant="secondary">{t("setupKind")}</Badge>
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
          objectKind: "setup",
          sharePath: `/${locale}/catalog/setups/${stableId}/versions/${summary.latest_version}`,
          likesCount: summary.likes_count,
          initiallyLiked,
          reportHref,
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
            report: reportLabel,
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
        main={
          <>
            {passport ? (
              <ObjectTechnicalDetails
                title={t("technicalDetails")}
                summary={summary.latest_lifecycle}
                facts={[
                  { label: t("lifecycle"), value: summary.latest_lifecycle },
                  { label: t("publishedAt"), value: summary.latest_published_at },
                  { label: t("harness"), value: summary.latest_harness_id },
                ]}
                licenseId={passport.license.spdx_id}
                licenseLabel={t("license")}
              />
            ) : null}
            {passport ? (
              <SetupComposition
                passport={passport}
                components={summary.latest_checks?.components ?? []}
                catalogComponents={catalogComponents}
                setupAuthor={{ accountId: ownerId, displayName: author?.display_name }}
                budget={budget}
                t={t}
              />
            ) : null}
            {aggregatedRequirements ? (
              <RequirementsSummary
                requirements={aggregatedRequirements}
                labels={requirementLabels(t, tc)}
              />
            ) : null}
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
              headingId="setup-author-heading"
            />
            <div className="border-border bg-card rounded-lg border p-4 shadow-sm">
              <CatalogUsageStats
                metrics={summary.usage_metrics}
                locale={locale}
                viewsLabel={t("detailViews")}
                downloadsLabel={t("artifactDownloads")}
              />
            </div>
            <ContextBudgetPanel
              budget={budget}
              command={impactCommand}
              labels={contextBudgetLabels(t, tCli)}
            />
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
              hrefFor={(version) => `/catalog/setups/${stableId}/versions/${version}`}
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

async function readAuthor(accountId: string): Promise<PublicProfileProjection | null> {
  try {
    return await readPublisherProfile(asAccountId(accountId));
  } catch {
    return null;
  }
}

async function isLiked(token: string, stableId: string) {
  try {
    const reactions = await listCatalogReactions(token);
    return reactions.items.some(
      (item) => item.object_kind === "setup" && item.summary.stable_id === stableId,
    );
  } catch {
    return false;
  }
}
