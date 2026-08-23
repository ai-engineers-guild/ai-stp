import { experimentalTrust } from "./catalog-ids";
import type { SafetyChecksSummary } from "@/lib/api/generated/types.gen";

export const missingSupport = {
  schema_version: 1 as const,
  tier: "primary" as const,
  state: "missing" as const,
  evidence: [],
};

export const betaMissingSupport = {
  schema_version: 1 as const,
  tier: "beta" as const,
  state: "missing" as const,
  evidence: [],
};

type SupportFixture = typeof missingSupport | typeof betaMissingSupport;

function defaultSupportForHarness(
  harnessId: ComponentSummaryFixture["latest_harness_id"],
): SupportFixture {
  return harnessId === "pi" || harnessId === "opencode" || harnessId === "grok-build"
    ? betaMissingSupport
    : missingSupport;
}

export type ComponentSummaryFixture = {
  schema_version: 1;
  stable_id: string;
  latest_version: string;
  latest_name: string;
  latest_description: string;
  latest_harness_id: "claude-code" | "codex" | "pi" | "opencode" | "grok-build";
  latest_harness_ids: Array<"claude-code" | "codex" | "pi" | "opencode" | "grok-build">;
  latest_component_type:
    "instruction" | "skill" | "mcp" | "hook" | "command" | "agent" | "plugin" | "setting";
  latest_projection_kind: "marketplace" | "plugin" | "native_files" | "package";
  latest_tags: string[];
  latest_lifecycle: "active" | "deprecated" | "blocked";
  latest_trust: typeof experimentalTrust;
  latest_support: SupportFixture;
  latest_checks: SafetyChecksSummary | null;
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
};

export type SetupSummaryFixture = {
  schema_version: 1;
  stable_id: string;
  latest_version: string;
  latest_name: string;
  latest_description: string;
  latest_purpose: string;
  latest_target_role: string;
  latest_harness_id: "claude-code" | "codex" | "pi" | "opencode" | "grok-build";
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
  > & {
    latest_lifecycle?: ComponentSummaryFixture["latest_lifecycle"];
    latest_trust?: typeof experimentalTrust;
    latest_support?: SupportFixture;
    latest_checks?: SafetyChecksSummary | null;
    latest_harness_ids?: ComponentSummaryFixture["latest_harness_ids"];
  },
): ComponentSummaryFixture {
  return {
    schema_version: 1,
    latest_lifecycle: "active",
    latest_trust: experimentalTrust,
    latest_support: defaultSupportForHarness(partial.latest_harness_id),
    latest_checks: null,
    publisher_id: partial.owner_id,
    likes_count: 0,
    github_stars: null,
    usage_metrics: null,
    latest_requirements_count: 0,
    latest_requires_credentials: false,
    updated_at: partial.latest_published_at,
    latest_harness_ids: [partial.latest_harness_id],
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
  > & {
    latest_lifecycle?: SetupSummaryFixture["latest_lifecycle"];
    latest_trust?: typeof experimentalTrust;
    latest_support?: SupportFixture;
    latest_checks?: null;
  },
): SetupSummaryFixture {
  return {
    schema_version: 1,
    latest_lifecycle: "active",
    latest_trust: experimentalTrust,
    latest_support: defaultSupportForHarness(partial.latest_harness_id),
    latest_checks: null,
    publisher_id: partial.owner_id,
    likes_count: 0,
    github_stars: null,
    usage_metrics: null,
    latest_requirements_count: 0,
    latest_requires_credentials: false,
    updated_at: partial.latest_published_at,
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
