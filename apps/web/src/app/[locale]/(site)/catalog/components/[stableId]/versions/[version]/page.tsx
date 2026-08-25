import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Badge } from "@/components/atoms/badge";
import { CatalogUsageStats } from "@/components/molecules/catalog-usage-stats";
import { CliCopyBlock } from "@/components/molecules/cli-copy-block";
import { ExactSourceLink } from "@/components/molecules/exact-source-link";
import { OsBadgeList } from "@/components/molecules/os-badge-list";
import { StatePanel } from "@/components/molecules/state-panel";
import {
  SafetyChecksSummaryView,
  safetyChecksLabels,
} from "@/components/molecules/safety-checks-summary";
import { SupportSummary, supportLabels } from "@/components/molecules/support-summary";
import { readComponentGithubMetadata, readComponentVersion } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/errors";
import { asVersionId, tryAsComponentId } from "@/lib/brands";
import { namedOperatingSystems, namedPassportHarnesses } from "@/lib/catalog-harnesses";
import { registryVersion } from "@/lib/cli-copy";
import { buildDeepLink, normalizeTarget } from "@/lib/deep-links";
import { publicOrigin } from "@/lib/site";
import { Link } from "@/lib/i18n/navigation";

type PageProps = {
  params: Promise<{ locale: string; stableId: string; version: string }>;
};

// The page intentionally renders the complete immutable passport in one server component.
// eslint-disable-next-line max-lines-per-function
export default async function ComponentVersionPage({ params }: PageProps) {
  const { locale, stableId, version } = await params;
  setRequestLocale(locale);
  const componentId = tryAsComponentId(stableId);
  if (!componentId) notFound();

  let response;
  try {
    response = await readComponentVersion(componentId, asVersionId(version));
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_NOT_FOUND") {
      notFound();
    }
    const tc = await getTranslations("common");
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  const t = await getTranslations("catalog");
  const tc = await getTranslations("common");
  const tCli = await getTranslations("cli");

  const passport = response.passport;
  const metadata = await readComponentGithubMetadata(componentId, asVersionId(version)).catch(
    () => ({ schema_version: 1 as const, stars: null, archived: null }),
  );
  const canonical = buildDeepLink(
    publicOrigin().origin,
    normalizeTarget({
      kind: "component",
      stable_id: stableId,
      version,
      locale: locale === "en" ? "en" : "ru",
      intent: "report",
    }),
  );

  return (
    <article className="min-w-0 space-y-6 overflow-x-clip">
      <p className="text-sm">
        <Link href={`/catalog/components/${stableId}`} className="underline">
          {t("backToObject")}
        </Link>
      </p>
      <h1 className="text-2xl font-medium tracking-tight break-words sm:text-3xl">
        {passport.name}@{passport.version}
      </h1>
      <p className="text-muted-foreground break-words">{passport.description}</p>
      <div className="flex flex-wrap gap-2">
        <Badge>{response.trust.trust_lane}</Badge>
        <Badge variant="secondary">{passport.component_type}</Badge>
        <Badge variant="outline">{passport.harness_id}</Badge>
      </div>
      <dl className="grid gap-3 sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground text-sm">{t("lifecycle")}</dt>
          <dd>{response.lifecycle}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-sm">{t("publishedAt")}</dt>
          <dd>{response.published_at}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-sm">{t("harness")}</dt>
          <dd>{namedPassportHarnesses(passport).join(", ")}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-sm">{t("supportedOs")}</dt>
          <dd>
            <OsBadgeList values={namedOperatingSystems(passport)} empty={t("noneListed")} />
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-sm">{t("type")}</dt>
          <dd>{passport.component_type}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-sm">{t("projectionKind")}</dt>
          <dd>{passport.projection_kind}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-sm">{t("license")}</dt>
          <dd>{passport.license.spdx_id}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-sm">{t("requiresCredentials")}</dt>
          <dd>{passport.requires_credentials ? tc("yes") : tc("no")}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-sm">{t("requiresAuthorization")}</dt>
          <dd>{passport.requires_authorization}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground text-sm">{t("publisher")}</dt>
          <dd>
            <Link href={`/publishers/${passport.owner_id}`} className="font-mono text-sm underline">
              {passport.owner_id}
            </Link>
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground text-sm">{t("tags")}</dt>
          <dd className="flex flex-wrap gap-1">
            {passport.tags.map((tag) => (
              <Badge key={tag} variant="outline">
                {tag}
              </Badge>
            ))}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground text-sm">{t("evidenceSummary")}</dt>
          <dd>
            {passport.compatibility_evidence_refs.length === 0
              ? t("noEvidence")
              : passport.compatibility_evidence_refs.join(", ")}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground text-sm">{t("passportDigest")}</dt>
          <dd className="font-mono text-xs break-all">{response.passport_digest}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-sm">{t("authorVerified")}</dt>
          <dd>{response.trust.author_verified ? tc("yes") : tc("no")}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-sm">{t("componentVerified")}</dt>
          <dd>{response.trust.component_verified ? tc("yes") : tc("no")}</dd>
        </div>
      </dl>
      <ExactSourceLink source={passport.source} label={t("viewSource")} />
      <CatalogUsageStats
        metrics={response.usage_metrics}
        locale={locale}
        viewsLabel={t("detailViews")}
        downloadsLabel={t("artifactDownloads")}
      />
      {metadata.stars !== null ? (
        <p className="text-sm">
          {t("githubStars")}: <span className="font-mono">{metadata.stars}</span>
        </p>
      ) : null}
      {metadata.archived === true ? (
        <p className="text-sm font-medium">{t("githubArchived")}</p>
      ) : null}
      <CliCopyBlock
        command={registryVersion("component", stableId, version)}
        title={tCli("useTitle")}
        description={canonical.cli_command}
        copyLabel={tCli("copy")}
        copiedLabel={tCli("copied")}
        errorLabel={tCli("copyError")}
        docsLabel={tCli("docs")}
      />
      <section id="report" className="border-border space-y-2 rounded-lg border p-3">
        <h2 className="text-lg font-medium tracking-tight">{t("reportSection")}</h2>
        <p className="text-muted-foreground text-sm">{t("reportSectionBody")}</p>
        <p className="font-mono text-xs break-all">{canonical.web_url}</p>
      </section>
      <SafetyChecksSummaryView summary={response.checks} labels={safetyChecksLabels(t)} />
      <SupportSummary support={response.support} labels={supportLabels(t)} />
    </article>
  );
}
