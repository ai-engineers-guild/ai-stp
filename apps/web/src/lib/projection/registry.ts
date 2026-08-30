import { getTranslations } from "next-intl/server";

import { tryAsAccountId, tryAsComponentId, tryAsSetupId, asVersionId } from "@/lib/brands";
import {
  catalogRelations,
  listExternalProducts,
  readComponent,
  readComponentGithubMetadata,
  readComponentVersion,
  readCountry,
  readExternalProduct,
  readSetup,
  readSetupVersion,
} from "@/lib/api/catalog";
import { readPublisherProfile } from "@/lib/api/public-profile";
import { catalogQueryToRecord, parseCatalogSearchParams } from "@/lib/catalog-query";
import { startCatalogResourceReads } from "@/lib/catalog-load";
import { INSTALL_CLI } from "@/lib/cli-copy";
import { docsSource } from "@/lib/docs-source";
import type { MachineDocument } from "@/lib/projection/machine-document";
import { PRIVATE_ROUTES } from "@/lib/projection/routes-private";
import {
  matchesPattern,
  type MachineRoute,
  type MachineRouteContext,
} from "@/lib/projection/route-table";
import {
  presentCatalog,
  presentComponentDetail,
  presentComponentVersion,
  presentDocs,
  presentLanding,
  presentLegal,
  presentPage,
  presentPublisher,
  presentSetupDetail,
  presentSetupVersion,
} from "@/lib/projection/presenters";
import {
  presentCountry,
  presentService,
  presentServicesIndex,
} from "@/lib/projection/regional-presenters";
import {
  componentFactsFromLoaders,
  countryPublicFacts,
  servicePublicFacts,
} from "@/lib/projection/page-facts";
import { isExternalCatalogEnabled } from "@/lib/projection/inventory";
import { orNotFound } from "@/lib/projection/not-found";
import { githubSourceUrl } from "@/lib/source-url";
import { publishedContent, findContent } from "@/lib/content/source";
import { presentContentEntry, presentContentIndex } from "@/lib/content/presenter";
import { isFeatureEnabled } from "@/lib/features/gate";

/** Labels shared by every object document (REQ-3610). */
async function objectLabels() {
  const t = await getTranslations("catalog");
  const tc = await getTranslations("common");
  const tm = await getTranslations("machineDoc");
  return {
    yes: tc("yes"),
    no: tc("no"),
    stableId: tm("stableId"),
    version: "version",
    digest: tm("digest"),
    harness: "harness",
    trustLane: tm("trustLane"),
    authorVerified: "author_verified",
    componentVerified: "component_verified",
    install: tm("install"),
    type: "component_type",
    purpose: t("purpose"),
    targetRole: t("targetRole"),
    publisher: t("author"),
    tags: t("tags"),
    lifecycle: t("lifecycle"),
    projectionKind: "projection_kind",
    dependencies: "dependencies",
    license: t("license"),
    publishedAt: t("publishedAt"),
    requiresCredentials: t("requiresCredentials"),
    requiresAuthorization: t("requiresAuthorization"),
    requiredEnv: t("requiredEnvironment"),
    requiresCapabilities: t("requiredCapabilities"),
    compatibility: t("compatibility"),
    checks: t("safetyChecks"),
    githubStars: t("githubStars"),
    detailViews: t("detailViews"),
    artifactDownloads: t("artifactDownloads"),
    none: t("noneListed"),
  };
}

/**
 * A generic document for a route that has no domain presenter yet: heading,
 * summary and the outgoing links of that section. Never a human tree
 * (REQ-3612).
 */
async function generic(
  namespace: string,
  titleKey: string,
  links: readonly (readonly [string, string])[],
  summaryKey?: string,
): Promise<MachineDocument> {
  const t = await getTranslations(namespace);
  return presentPage({
    title: t(titleKey),
    ...(summaryKey ? { summary: t(summaryKey) } : {}),
    links,
  });
}

const PUBLIC_ROUTES: MachineRoute[] = [
  {
    pattern: "",
    resolve: async () => {
      const t = await getTranslations("landing");
      return presentLanding({
        title: t("title"),
        subtitle: t("subtitle"),
        browseCatalog: t("browseCatalog"),
        installCommand: INSTALL_CLI,
        installHeading: t("installHeading"),
      });
    },
  },
  {
    pattern: "catalog",
    resolve: async ({ searchParams }) => {
      const t = await getTranslations("catalog");
      const parsed = parseCatalogSearchParams(searchParams);
      if (!parsed.ok) {
        const details = [
          ...parsed.unknownKeys.map((key) => `${t("unknownFilter")}: ${key}`),
          ...parsed.invalidTags.map((tag) => `${t("invalidTag")}: ${tag}`),
          ...parsed.invalidSupport.map((filter) => `${t("invalidSupport")}: ${filter}`),
          ...parsed.invalidQuery.map((error) => `${t("invalidQuery")}: ${error}`),
        ];
        return presentPage({
          title: t("title"),
          summary: t("filterError"),
          fields: details.map((item) => [t("filterError"), item] as const),
          links: [
            ["Home", "/"],
            ["Catalog", "/catalog"],
          ],
        });
      }
      const started = startCatalogResourceReads(parsed.value);
      const [components, setups] = await Promise.all([started.components, started.setups]);
      return presentCatalog({
        title: t("title"),
        subtitle: t("subtitle"),
        components: components ? [...components.items, ...components.experimental] : [],
        setups: setups ? [...setups.items, ...setups.experimental] : [],
        labels: await objectLabels(),
        emptyMessage: t("emptyAll"),
        queryFields: Object.entries(catalogQueryToRecord(parsed.value)),
      });
    },
  },
  {
    pattern: "catalog/components/:stableId",
    resolve: async ({ segments }) => {
      const componentId = tryAsComponentId(segments[2] ?? "");
      if (!componentId) return null;
      const detail = await orNotFound(readComponent(componentId));
      if (!detail) return null;
      const latest = await readComponentVersion(
        componentId,
        asVersionId(detail.summary.latest_version),
      ).catch(() => null);
      const relations = catalogRelations(detail);
      const github = latest
        ? await readComponentGithubMetadata(
            componentId,
            asVersionId(detail.summary.latest_version),
          ).catch(() => ({ stars: null, archived: null }))
        : { stars: null, archived: null };
      return presentComponentDetail({
        facts: componentFactsFromLoaders({
          summary: detail.summary,
          digest:
            latest?.passport_digest ??
            detail.versions.find((item) => item.version === detail.summary.latest_version)
              ?.passport_digest ??
            "",
          relations: {
            countryCodes: relations.country_codes,
            services: relations.services.map((item) => item.canonical_domain),
          },
          passport: latest?.passport ?? null,
          publishedAt: latest?.published_at ?? detail.summary.latest_published_at,
          versions: detail.versions.map((item) => item.version),
          sourceUrl: latest ? githubSourceUrl(latest.passport.source) : null,
          github,
          checks: latest?.checks ?? detail.summary.latest_checks,
          usage: detail.summary.usage_metrics,
        }),
        labels: await objectLabels(),
      });
    },
  },
  {
    pattern: "catalog/components/:stableId/versions/:version",
    resolve: async ({ segments }) => {
      const componentId = tryAsComponentId(segments[2] ?? "");
      if (!componentId) return null;
      const response = await orNotFound(
        readComponentVersion(componentId, asVersionId(segments[4] ?? "")),
      );
      if (!response) return null;
      const passport = response.passport;
      const github = await readComponentGithubMetadata(
        componentId,
        asVersionId(segments[4] ?? ""),
      ).catch(() => ({ stars: null, archived: null }));
      return presentComponentVersion({
        facts: componentFactsFromLoaders({
          summary: {
            stable_id: componentId,
            publisher_id: passport.owner_id,
            latest_name: passport.name,
            latest_description: passport.description,
            latest_version: passport.version,
            latest_harness_id: passport.harness_id,
            latest_component_type: passport.component_type,
            latest_lifecycle: response.lifecycle,
            latest_tags: passport.tags,
            latest_trust: response.trust,
            latest_projection_kind: passport.projection_kind,
          },
          digest: response.passport_digest,
          passport,
          publishedAt: response.published_at,
          versions: [passport.version],
          sourceUrl: githubSourceUrl(passport.source),
          github,
          checks: response.checks,
          usage: response.usage_metrics,
        }),
        labels: await objectLabels(),
      });
    },
  },
  {
    pattern: "catalog/setups/:stableId",
    resolve: async ({ segments }) => {
      const setupId = tryAsSetupId(segments[2] ?? "");
      if (!setupId) return null;
      const detail = await orNotFound(readSetup(setupId));
      if (!detail) return null;
      const relations = catalogRelations(detail);
      return presentSetupDetail({
        summary: detail.summary,
        passportDigest: detail.versions[0]?.passport_digest ?? "",
        labels: await objectLabels(),
        countryCodes: relations.country_codes,
        services: relations.services.map((item) => item.canonical_domain),
      });
    },
  },
  {
    pattern: "catalog/setups/:stableId/versions/:version",
    resolve: async ({ segments }) => {
      const setupId = tryAsSetupId(segments[2] ?? "");
      if (!setupId) return null;
      const stableId = setupId;
      const response = await orNotFound(readSetupVersion(setupId, asVersionId(segments[4] ?? "")));
      if (!response) return null;
      const passport = response.passport;
      return presentSetupVersion({
        stableId,
        name: passport.name,
        version: passport.version,
        description: passport.description,
        digest: response.passport_digest,
        harness: passport.harness_id,
        purpose: passport.purpose,
        targetRole: passport.target_role,
        posture: passport.posture,
        trust: response.trust,
        ownerId: passport.owner_id,
        tags: passport.tags,
        labels: await objectLabels(),
        usage: response.usage_metrics,
      });
    },
  },
  {
    pattern: "publishers/:account",
    resolve: async ({ segments }) => {
      const accountId = tryAsAccountId(segments[1] ?? "");
      if (!accountId) return null;
      const t = await getTranslations("publisher");
      const profile = await orNotFound(readPublisherProfile(accountId));
      if (!profile) return null;
      return presentPublisher({
        title: t("title"),
        accountId: profile.account_id,
        displayName: profile.display_name,
        bio: profile.bio,
        links: profile.links.map((item) => ({ label: item.label, url: item.url })),
        componentIds: [],
        setupIds: [],
        emptyProfile: t("empty"),
      });
    },
  },
  {
    pattern: "legal/:slug",
    feature: "saas_public_pages",
    resolve: async ({ segments, locale }) => {
      const slug = segments[1] ?? "";
      const t = await getTranslations("legal");
      return presentLegal({
        title: t(`${slug}.title`),
        body: t(`${slug}.body`),
        version: "1.0",
        effective: "2026-08-05",
        language: locale,
        versionLabel: t("version"),
        effectiveLabel: t("effective"),
        languageLabel: t("language"),
        policyLinks: ["privacy", "cookies", "service-rules", "licensing"].map((item) => ({
          title: t(`${item}.title`),
          href: `/legal/${item}`,
        })),
      });
    },
  },
  {
    pattern: "docs/*",
    resolve: ({ locale, segments }) => {
      const slug = segments.slice(1);
      const page = docsSource.getPage([locale, ...slug]);
      const nav = docsSource
        .getPages()
        .filter((item) => item.slugs[0] === locale)
        .map((item) => ({
          title: item.data.title,
          href: `/docs/${item.slugs.slice(1).join("/")}`,
        }));
      if (!page) {
        return presentDocs({ title: "Documentation", description: null, bodyText: "", nav });
      }
      return presentDocs({
        title: page.data.title,
        description: page.data.description ?? null,
        bodyText: page.data.content,
        nav,
      });
    },
  },
  {
    pattern: "content",
    feature: "content_hub",
    resolve: ({ locale }) => presentContentIndex(publishedContent(locale)),
  },
  {
    pattern: "content/:type/:slug",
    feature: "content_hub",
    resolve: ({ locale, segments }) => {
      const entry = findContent(locale, segments[1] ?? "", segments[2] ?? "");
      return entry ? presentContentEntry(entry) : null;
    },
  },
  {
    pattern: "services",
    resolve: async () => {
      const t = await getTranslations("regionalServices");
      const services = await listExternalProducts()
        .then((result) => result.items)
        .catch(() => []);
      return presentServicesIndex({
        title: t("title"),
        subtitle: t("subtitle"),
        emptyMessage: t("empty"),
        services: services.map((item) => ({ name: item.name, domain: item.canonical_domain })),
      });
    },
  },
  {
    pattern: "services/:domain",
    resolve: async ({ segments }) => {
      if (!isExternalCatalogEnabled()) return null;
      const service = await readExternalProduct(segments[1] ?? "").catch(() => null);
      if (!service) return null;
      return presentService(servicePublicFacts(service));
    },
  },
  {
    pattern: "countries/:code",
    resolve: async ({ locale, segments }) => {
      if (!isExternalCatalogEnabled()) return null;
      const country = await readCountry(segments[1] ?? "").catch(() => null);
      if (!country) return null;
      const facts = countryPublicFacts(country);
      const display =
        new Intl.DisplayNames([locale], { type: "region" }).of(facts.code) ?? facts.code;
      return presentCountry({
        title: display,
        code: facts.code,
        services: facts.services,
        objects: facts.objects,
      });
    },
  },
  {
    pattern: "contact",
    feature: "saas_public_pages",
    resolve: async () => {
      const t = await getTranslations("contact");
      return presentPage({
        title: t("title"),
        summary: t("subtitle"),
        fields: [
          [t("formTitle"), t("formHint")],
          [t("responseTitle"), t("responseHint")],
          [t("privacyHint"), t("privacyHint")],
        ],
        links: [["catalog", "/catalog"]],
      });
    },
  },
  {
    pattern: "login",
    resolve: () => generic("login", "title", [["catalog", "/catalog"]], "subtitle"),
  },
  {
    pattern: "device-login",
    resolve: () => generic("deviceLogin", "title", [["devices", "/devices"]], "subtitle"),
  },
];

const ROUTES: MachineRoute[] = [...PUBLIC_ROUTES, ...PRIVATE_ROUTES];

/** The machine document for a page path, or null when no route matches. */
export async function resolveMachineDocument(
  ctx: MachineRouteContext,
): Promise<MachineDocument | null> {
  const route = ROUTES.find(
    (candidate) =>
      matchesPattern(candidate.pattern, ctx.segments) &&
      (candidate.feature === undefined || isFeatureEnabled(candidate.feature)),
  );
  if (!route) return null;
  return route.resolve(ctx);
}

/** Route patterns covered by the machine tree, for coverage tests. */
export const MACHINE_ROUTE_PATTERNS = ROUTES.map((route) => route.pattern);
