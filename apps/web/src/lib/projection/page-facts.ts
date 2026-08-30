/* eslint-disable max-lines -- public catalog facts stay in one owner module */
import type { ExternalProduct, Country } from "@/lib/api/catalog";
import { namedHarnesses } from "@/lib/catalog-harnesses";
import { registryCommand } from "@/lib/cli-copy";
import { isComponentType, type ComponentTypeId } from "@/lib/projection/inventory";

type TrustLike = {
  trust_lane: string;
  author_verified: boolean;
  component_verified: boolean;
};

export type ComponentSummaryFacts = {
  stable_id: string;
  publisher_id: string;
  latest_name: string;
  latest_description: string;
  latest_version: string;
  latest_harness_id: string;
  latest_harness_ids?: string[];
  latest_component_type: string;
  latest_lifecycle: string;
  latest_tags: string[];
  latest_trust: TrustLike;
  latest_projection_kind?: string;
  latest_requires_credentials?: boolean;
  latest_published_at?: string;
  usage_metrics?: {
    detail_views_count: number;
    artifact_downloads_count: number;
  } | null;
};

export type SetupSummaryFacts = {
  stable_id: string;
  publisher_id: string;
  latest_name: string;
  latest_description: string;
  latest_version: string;
  latest_harness_id: string;
  latest_purpose: string;
  latest_target_role: string | null;
  latest_posture: string | null;
  latest_lifecycle: string;
  latest_tags: string[];
  latest_trust: TrustLike;
  usage_metrics?: {
    detail_views_count: number;
    artifact_downloads_count: number;
  } | null;
};

export type PublicDependency = {
  stableId: string;
  version: string;
};

export type PublicObjectFacts = {
  stableId: string;
  name: string;
  version: string;
  description: string;
  digest: string;
  harness: string;
  componentType?: ComponentTypeId;
  projectionKind?: string;
  purpose?: string;
  // `| undefined` spelled out because the project runs with
  // `exactOptionalPropertyTypes`: an optional key and a key that may be
  // explicitly undefined are different types there.
  targetRole?: string | undefined;
  posture?: string | undefined;
  trustLane: string;
  authorVerified: boolean;
  componentVerified: boolean;
  lifecycle?: string;
  publisher?: string;
  tags: string[];
  install: string;
  countryCodes: string[];
  services: string[];
  license?: string;
  requiresCredentials?: boolean;
  requiresAuthorization?: string;
  requiredEnv: ReadonlyArray<{ name: string; purpose: string }>;
  dependencies: readonly PublicDependency[];
  requiresCapabilities: readonly string[];
  compatibilityEvidence: readonly string[];
  publishedAt?: string;
  versions: readonly string[];
  sourceUrl?: string | null;
  githubStars?: number | null;
  githubArchived?: boolean | null;
  checksSummary?: string | null;
  detailViewsCount?: number | null;
  artifactDownloadsCount?: number | null;
};

export type ComponentPublicExtras = {
  countryCodes?: string[] | undefined;
  services?: string[] | undefined;
  projectionKind?: string | undefined;
  license?: string | undefined;
  requiresCredentials?: boolean | undefined;
  requiresAuthorization?: string | undefined;
  requiredEnv?: ReadonlyArray<{ name: string; purpose: string }> | undefined;
  dependencies?: readonly PublicDependency[] | undefined;
  requiresCapabilities?: readonly string[] | undefined;
  compatibilityEvidence?: readonly string[] | undefined;
  publishedAt?: string | undefined;
  versions?: readonly string[] | undefined;
  sourceUrl?: string | null | undefined;
  githubStars?: number | null | undefined;
  githubArchived?: boolean | null | undefined;
  checksSummary?: string | null | undefined;
  usageMetrics?: {
    detail_views_count: number;
    artifact_downloads_count: number;
  } | null;
};

export type ComponentPassportFactsInput = {
  projection_kind: string;
  license: { spdx_id: string };
  requires_credentials: boolean;
  requires_authorization: string;
  required_env: ReadonlyArray<{ name: string; purpose: string }>;
  requires_components: ReadonlyArray<{ stable_id: string; version: string }>;
  requires_capabilities?: readonly string[];
  compatibility_evidence_refs?: readonly string[];
};

export type CountryFacts = {
  code: string;
  services: ReadonlyArray<{ name: string; domain: string }>;
  objects: ReadonlyArray<{ name: string; kind: string; stableId: string }>;
};

export type ServiceFacts = {
  name: string;
  domain: string;
  primaryUrl: string;
  countryCodes: string[];
  objects: ReadonlyArray<{ name: string; kind: string; stableId: string }>;
};

export type OwnerObjectFacts = {
  name: string;
  kind: string;
  stableId: string;
  versions: ReadonlyArray<{ version: string; digest: string | null }>;
  attachedDomains: string[];
};

export type OwnerVersionFacts = {
  name: string;
  kind: string;
  stableId: string;
  version: string;
  lifecycle: string;
  visibility: string;
  digest: string | null;
  authorVerified: boolean;
  componentVerified: boolean;
  installEligible: boolean;
};

export type PublicationFacts = {
  planId: string;
  state: string;
  objectKind: string;
  stableId: string;
  version: string;
  digest: string;
  planHash: string;
  policy: string;
  expiresAt: string;
  effects: string[];
};

export type InvitationFacts = {
  invitationId: string;
};

export type StaffCaseFacts = {
  caseId: string;
  state: string;
  vulnerability: boolean;
  objectKind: string;
  stableId: string;
  version: string;
  digest: string | null;
  errorCode: string;
  harnessId: string;
};

export type AccountPrivacyFacts = {
  showProfilePublicly: boolean;
  allowPublisherListing: boolean;
};

export type AccountProfileFacts = {
  displayName: string | null;
  bio: string | null;
  links: ReadonlyArray<{ label: string; url: string }>;
};

const LEAKAGE =
  /avatar_url|avatar_asset|csrf|session_token|authorization_token|password|secret|api_key|operation_id|media_url|youtube|catalog-art|\/v1\/media\//i;

/** Public component facts shown on the human detail page, without media. */
// eslint-disable-next-line complexity -- existing optional passport extras
export function componentPublicFacts(
  summary: ComponentSummaryFacts,
  digest: string,
  extras?: ComponentPublicExtras,
): PublicObjectFacts {
  const projectionKind = extras?.projectionKind ?? summary.latest_projection_kind;
  const facts: PublicObjectFacts = {
    stableId: summary.stable_id,
    name: summary.latest_name,
    version: summary.latest_version,
    description: summary.latest_description,
    digest,
    harness: namedHarnesses(summary).join(", "),
    trustLane: summary.latest_trust.trust_lane,
    authorVerified: summary.latest_trust.author_verified,
    componentVerified: summary.latest_trust.component_verified,
    lifecycle: summary.latest_lifecycle,
    publisher: summary.publisher_id,
    tags: [...summary.latest_tags],
    install: registryCommand(summary.stable_id, summary.latest_version),
    countryCodes: extras?.countryCodes ?? [],
    services: extras?.services ?? [],
    requiredEnv: extras?.requiredEnv ?? [],
    dependencies: extras?.dependencies ?? [],
    requiresCapabilities: extras?.requiresCapabilities ?? [],
    compatibilityEvidence: extras?.compatibilityEvidence ?? [],
    versions: extras?.versions ?? [summary.latest_version],
    sourceUrl: extras?.sourceUrl ?? null,
    githubStars: extras?.githubStars ?? null,
    githubArchived: extras?.githubArchived ?? null,
    checksSummary: extras?.checksSummary ?? null,
  };
  applyUsageFacts(facts, extras?.usageMetrics ?? summary.usage_metrics);
  if (isComponentType(summary.latest_component_type)) {
    facts.componentType = summary.latest_component_type;
  }
  if (projectionKind) facts.projectionKind = projectionKind;
  if (extras?.license) facts.license = extras.license;
  if (extras?.requiresCredentials !== undefined) {
    facts.requiresCredentials = extras.requiresCredentials;
  } else if (summary.latest_requires_credentials !== undefined) {
    facts.requiresCredentials = summary.latest_requires_credentials;
  }
  if (extras?.requiresAuthorization) {
    facts.requiresAuthorization = extras.requiresAuthorization;
  }
  const publishedAt = extras?.publishedAt ?? summary.latest_published_at;
  if (publishedAt) {
    facts.publishedAt = publishedAt;
  }
  return facts;
}

/** Map the same catalog loaders the human page uses onto public facts. */
export function componentFactsFromLoaders(input: {
  summary: ComponentSummaryFacts;
  digest: string;
  relations?: { countryCodes?: string[]; services?: string[] };
  passport?: ComponentPassportFactsInput | null;
  publishedAt?: string;
  versions?: readonly string[];
  sourceUrl?: string | null;
  github?: { stars: number | null; archived: boolean | null };
  checks?: { passed: number; total_countable: number; status: string } | null;
  usage?: {
    detail_views_count: number;
    artifact_downloads_count: number;
  } | null;
}): PublicObjectFacts {
  const passport = input.passport;
  return componentPublicFacts(input.summary, input.digest, {
    countryCodes: input.relations?.countryCodes,
    services: input.relations?.services,
    projectionKind: passport?.projection_kind ?? input.summary.latest_projection_kind,
    license: passport?.license.spdx_id,
    requiresCredentials:
      passport?.requires_credentials ?? input.summary.latest_requires_credentials,
    requiresAuthorization: passport?.requires_authorization,
    requiredEnv: passport?.required_env,
    dependencies: passport?.requires_components.map((item) => ({
      stableId: item.stable_id,
      version: item.version,
    })),
    requiresCapabilities: passport?.requires_capabilities,
    compatibilityEvidence: passport?.compatibility_evidence_refs,
    publishedAt: input.publishedAt ?? input.summary.latest_published_at,
    versions: input.versions,
    sourceUrl: input.sourceUrl,
    githubStars: input.github?.stars,
    githubArchived: input.github?.archived,
    checksSummary: input.checks
      ? `${String(input.checks.passed)} / ${String(input.checks.total_countable)} ${input.checks.status}`
      : null,
    usageMetrics: input.usage ?? input.summary.usage_metrics ?? null,
  });
}

/** Public setup facts shown on the human detail page, without media. */
export function setupPublicFacts(
  summary: SetupSummaryFacts,
  digest: string,
  extras?: { countryCodes?: string[]; services?: string[] },
): PublicObjectFacts {
  const facts: PublicObjectFacts = {
    stableId: summary.stable_id,
    name: summary.latest_name,
    version: summary.latest_version,
    description: summary.latest_description,
    digest,
    harness: summary.latest_harness_id,
    purpose: summary.latest_purpose,
    // `?? undefined`, not `?? ""`: this shape marks an absent fact by omitting
    // the key, where the machine document marks it with an empty value. Two
    // conventions because they answer different readers.
    targetRole: summary.latest_target_role ?? undefined,
    posture: summary.latest_posture ?? undefined,
    trustLane: summary.latest_trust.trust_lane,
    authorVerified: summary.latest_trust.author_verified,
    componentVerified: summary.latest_trust.component_verified,
    lifecycle: summary.latest_lifecycle,
    publisher: summary.publisher_id,
    tags: [...summary.latest_tags],
    install: registryCommand(summary.stable_id, summary.latest_version),
    countryCodes: extras?.countryCodes ?? [],
    services: extras?.services ?? [],
    requiredEnv: [],
    dependencies: [],
    requiresCapabilities: [],
    compatibilityEvidence: [],
    versions: [summary.latest_version],
  };
  applyUsageFacts(facts, summary.usage_metrics);
  return facts;
}

function applyUsageFacts(
  facts: PublicObjectFacts,
  usage?: { detail_views_count: number; artifact_downloads_count: number } | null,
): void {
  if (!usage) return;
  facts.detailViewsCount = usage.detail_views_count;
  facts.artifactDownloadsCount = usage.artifact_downloads_count;
}

export function countryPublicFacts(country: Country): CountryFacts {
  return {
    code: country.code,
    services: country.services.map((item) => ({
      name: item.name,
      domain: item.canonical_domain,
    })),
    objects: country.objects.map((item) => ({
      name: item.name,
      kind: item.object_kind,
      stableId: item.stable_id,
    })),
  };
}

export function servicePublicFacts(service: ExternalProduct): ServiceFacts {
  return {
    name: service.name,
    domain: service.canonical_domain,
    primaryUrl: service.primary_url,
    countryCodes: [...service.country_codes],
    objects: (service.objects ?? []).map((item) => ({
      name: item.name,
      kind: item.object_kind,
      stableId: item.stable_id,
    })),
  };
}

export function ownerObjectPublicFacts(input: {
  name: string;
  object_kind: string;
  stable_id: string;
  versions: ReadonlyArray<{ version: string; content_digest?: string | null }>;
  attachedDomains?: readonly string[];
}): OwnerObjectFacts {
  return {
    name: input.name,
    kind: input.object_kind,
    stableId: input.stable_id,
    versions: input.versions.map((item) => ({
      version: item.version,
      digest: item.content_digest ?? null,
    })),
    attachedDomains: [...(input.attachedDomains ?? [])],
  };
}

export function ownerVersionPublicFacts(input: {
  name: string;
  object_kind: string;
  stable_id: string;
  version: string;
  lifecycle_state: string;
  visibility: string;
  content_digest: string | null;
  author_verified: boolean;
  component_verified: boolean;
  install_eligible: boolean;
}): OwnerVersionFacts {
  return {
    name: input.name,
    kind: input.object_kind,
    stableId: input.stable_id,
    version: input.version,
    lifecycle: input.lifecycle_state,
    visibility: input.visibility,
    digest: input.content_digest,
    authorVerified: input.author_verified,
    componentVerified: input.component_verified,
    installEligible: input.install_eligible,
  };
}

export function publicationPublicFacts(input: {
  plan_id: string;
  state: string;
  object_kind: string;
  stable_id: string;
  version: string;
  content_digest: string;
  plan_hash: string;
  policy_version: string;
  expires_at: string;
  effects: readonly string[];
}): PublicationFacts {
  return {
    planId: input.plan_id,
    state: input.state,
    objectKind: input.object_kind,
    stableId: input.stable_id,
    version: input.version,
    digest: input.content_digest,
    planHash: input.plan_hash,
    policy: input.policy_version,
    expiresAt: input.expires_at,
    effects: [...input.effects],
  };
}

export function invitationPublicFacts(invitationId: string): InvitationFacts {
  return { invitationId };
}

export function staffCasePublicFacts(input: {
  case_id: string;
  state: string;
  vulnerability: boolean;
  object_kind: string;
  stable_id: string;
  version: string;
  content_digest: string | null;
  error_code: string;
  harness_id: string;
}): StaffCaseFacts {
  return {
    caseId: input.case_id,
    state: input.state,
    vulnerability: input.vulnerability,
    objectKind: input.object_kind,
    stableId: input.stable_id,
    version: input.version,
    digest: input.content_digest,
    errorCode: input.error_code,
    harnessId: input.harness_id,
  };
}

export function accountPrivacyPublicFacts(input: {
  showProfilePublicly: boolean;
  allowPublisherListing: boolean;
}): AccountPrivacyFacts {
  return {
    showProfilePublicly: input.showProfilePublicly,
    allowPublisherListing: input.allowPublisherListing,
  };
}

export function accountProfilePublicFacts(input: {
  display_name: string | null;
  bio: string | null;
  links: ReadonlyArray<{ label: string; url: string }>;
}): AccountProfileFacts {
  return {
    displayName: input.display_name,
    bio: input.bio,
    links: input.links.map((item) => ({ label: item.label, url: item.url })),
  };
}

/** True when serialized machine text contains a forbidden leakage class. */
export function machineTextLeaks(text: string): boolean {
  return LEAKAGE.test(text);
}
