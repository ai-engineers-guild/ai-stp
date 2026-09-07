import { experimentalTrust } from "./catalog-ids";
import type { CatalogSupport, HarnessId, SafetyChecksSummary } from "@/lib/api/generated/types.gen";

export const missingSupport = {
  schema_version: 1 as const,
  tier: "beta" as const,
  state: "missing" as const,
  evidence: [],
};

type SupportFixture = CatalogSupport;

export type ComponentSummaryFixture = {
  schema_version: 1;
  stable_id: string;
  canonical_name: string;
  display_locale: "ru" | "en" | "";
  display_name: string;
  latest_version: string;
  latest_name: string;
  latest_description: string;
  latest_harness_id: HarnessId;
  latest_harness_ids: HarnessId[];
  latest_component_type:
    "instruction" | "skill" | "mcp" | "hook" | "command" | "agent" | "plugin" | "setting" | "cli";
  latest_projection_kind: "marketplace" | "plugin" | "native_files" | "package";
  latest_tags: string[];
  latest_lifecycle: "active" | "deprecated" | "blocked";
  latest_trust: typeof experimentalTrust;
  latest_support: SupportFixture;
  latest_checks: SafetyChecksSummary | null;
  latest_published_at: string;
  owner_id: string;
  owner_account_id: string;
  owner_handle: string;
  publisher_id: string;
  likes_count: number;
  github_stars: number | null;
  usage_metrics: {
    schema_version: 1;
    detail_views_count: number;
    artifact_downloads_count: number;
  } | null;
  latest_requirements_count: number;
  latest_requires_credentials: boolean;
  updated_at: string;
  latest_assurance: { verified_targets: number; assessed_targets: number };
};

export type SetupSummaryFixture = {
  schema_version: 1;
  stable_id: string;
  latest_version: string;
  latest_name: string;
  latest_description: string;
  latest_purpose: string;
  latest_target_role: string | null;
  latest_posture: string | null;
  latest_harness_id: ComponentSummaryFixture["latest_harness_id"];
  latest_harness_ids: Array<ComponentSummaryFixture["latest_harness_id"]>;
  latest_tags: string[];
  latest_lifecycle: "active" | "deprecated" | "blocked";
  latest_trust: typeof experimentalTrust;
  latest_support: SupportFixture;
  latest_checks: null;
  latest_published_at: string;
  owner_id: string;
  publisher_id: string;
  likes_count: number;
  github_stars: number | null;
  usage_metrics: {
    schema_version: 1;
    detail_views_count: number;
    artifact_downloads_count: number;
  } | null;
  latest_requirements_count: number;
  latest_requires_credentials: boolean;
  updated_at: string;
  family_id: string | null;
  family_match_kind: "family" | "member_harness" | "alignment" | null;
  family_member_count: number | null;
  composition: ReadonlyArray<{
    stable_id: string;
    version: string;
    passport_digest: string;
    variant_id: null;
  }>;
};

export function makeComponentSummary(
  partial: Omit<
    ComponentSummaryFixture,
    | "schema_version"
    | "latest_lifecycle"
    | "latest_trust"
    | "latest_support"
    | "latest_checks"
    | "publisher_id"
    | "likes_count"
    | "github_stars"
    | "usage_metrics"
    | "latest_requirements_count"
    | "latest_requires_credentials"
    | "updated_at"
    | "latest_harness_ids"
    | "canonical_name"
    | "display_locale"
    | "display_name"
    | "owner_account_id"
    | "owner_handle"
    | "latest_assurance"
  > & {
    latest_lifecycle?: ComponentSummaryFixture["latest_lifecycle"];
    latest_trust?: typeof experimentalTrust;
    latest_support?: SupportFixture;
    latest_checks?: SafetyChecksSummary | null;
    latest_harness_ids?: ComponentSummaryFixture["latest_harness_ids"];
    latest_assurance?: ComponentSummaryFixture["latest_assurance"];
  },
): ComponentSummaryFixture {
  return {
    schema_version: 1,
    latest_lifecycle: "active",
    latest_trust: experimentalTrust,
    latest_support: missingSupport,
    latest_checks: null,
    publisher_id: partial.owner_id,
    likes_count: 0,
    github_stars: null,
    usage_metrics: null,
    latest_requirements_count: 0,
    latest_requires_credentials: false,
    updated_at: partial.latest_published_at,
    latest_harness_ids: [partial.latest_harness_id],
    canonical_name: partial.latest_name,
    display_locale: "en",
    display_name: partial.latest_name,
    owner_account_id: partial.owner_id,
    owner_handle: partial.owner_id,
    latest_assurance: { verified_targets: 0, assessed_targets: 0 },
    ...partial,
  };
}

export function makeSetupSummary(
  partial: Omit<
    SetupSummaryFixture,
    | "schema_version"
    | "latest_lifecycle"
    | "latest_trust"
    | "latest_support"
    | "latest_checks"
    | "publisher_id"
    | "likes_count"
    | "github_stars"
    | "usage_metrics"
    | "latest_requirements_count"
    | "latest_requires_credentials"
    | "updated_at"
    | "latest_harness_ids"
    | "family_id"
    | "family_match_kind"
    | "family_member_count"
  > & {
    latest_lifecycle?: SetupSummaryFixture["latest_lifecycle"];
    latest_trust?: typeof experimentalTrust;
    latest_support?: SupportFixture;
    latest_checks?: null;
    latest_harness_ids?: SetupSummaryFixture["latest_harness_ids"];
    family_id?: SetupSummaryFixture["family_id"];
    family_match_kind?: SetupSummaryFixture["family_match_kind"];
    family_member_count?: SetupSummaryFixture["family_member_count"];
  },
): SetupSummaryFixture {
  return {
    schema_version: 1,
    latest_lifecycle: "active",
    latest_trust: experimentalTrust,
    latest_support: missingSupport,
    latest_checks: null,
    publisher_id: partial.owner_id,
    likes_count: 0,
    github_stars: null,
    usage_metrics: null,
    latest_requirements_count: 0,
    latest_requires_credentials: false,
    updated_at: partial.latest_published_at,
    latest_harness_ids: [partial.latest_harness_id],
    family_id: null,
    family_match_kind: null,
    family_member_count: null,
    ...partial,
  };
}

export function pin(stableId: string, version = "1.0") {
  return {
    stable_id: stableId,
    variant_id: null,
    version,
    passport_digest: "sha256:" + "0".repeat(64),
  };
}
