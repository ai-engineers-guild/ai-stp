import type { SafetyCheckEntry, TargetMatrix } from "@/lib/api/generated/types.gen";

import { FIXTURE_ACCOUNT_ID, FIXTURE_TIMESTAMP } from "./identity";
import {
  FIXTURE_COMPONENT_ID,
  FIXTURE_SETUP_ID,
  SEED_MULTI_HARNESS_COMPONENT_ID,
  ZERO_DIGEST,
  experimentalTrust,
} from "./catalog-ids";
import {
  makeComponentSummary,
  makeSetupSummary,
  missingSupport,
  pin,
  type ComponentSummaryFixture,
  type SetupSummaryFixture,
} from "./catalog-types";
import { multiAuthorComponents, multiAuthorSetups } from "./catalog-seed";

export type { ComponentSummaryFixture, SetupSummaryFixture } from "./catalog-types";
export { makeComponentSummary, makeSetupSummary } from "./catalog-types";
export {
  codexComponentSummary,
  piComponentSummary,
  opencodeComponentSummary,
  codexSetupSummary,
  piSetupSummary,
} from "./catalog-seed";

// A digest per version, not one shared placeholder. With every row carrying the
// same bytes, a projection pairing the newest version label with the oldest
// row's digest looked correct in every test — which is how it reached the live
// site.
function versionDigest(version: string): string {
  return `sha256:${version.replaceAll(".", "")}`.padEnd(ZERO_DIGEST.length, "0");
}

function versionEntry(
  version: string,
  publishedAt: string = FIXTURE_TIMESTAMP,
  support: ComponentSummaryFixture["latest_support"] = missingSupport,
) {
  return {
    version,
    passport_digest: versionDigest(version),
    lifecycle: "active" as const,
    trust: experimentalTrust,
    support,
    published_at: publishedAt,
  };
}

export const componentSummaryFixture = makeComponentSummary({
  stable_id: FIXTURE_COMPONENT_ID,
  latest_version: "1.2",
  latest_name: "pytest-guard-skill",
  latest_description:
    "Runs focused pytest subsets, surfaces failing assertions, and proposes minimal fixes for Claude Code sessions.",
  latest_harness_id: "claude-code",
  latest_harness_ids: ["claude-code", "codex"],
  latest_component_type: "skill",
  latest_projection_kind: "native_files",
  latest_tags: ["python", "tests"],
  latest_published_at: FIXTURE_TIMESTAMP,
  owner_id: FIXTURE_ACCOUNT_ID,
  latest_checks: {
    schema_version: 1,
    status: "available",
    checks_passed_percent: 86,
    coverage_complete: true,
    passed: 6,
    failed: 1,
    warning: 0,
    not_run: 0,
    total_countable: 7,
    components: [],
    checks: [
      {
        schema_version: 1,
        check_id: "structure",
        family: "passport",
        mandatory: true,
        result: "passed",
        reason: null,
        finding_summary: null,
        source: "platform_structure_verified",
      },
      {
        schema_version: 1,
        check_id: "digest",
        family: "integrity",
        mandatory: true,
        result: "passed",
        reason: null,
        finding_summary: null,
        source: "platform_digest_verified",
      },
      {
        schema_version: 1,
        check_id: "artifact_unpack",
        family: "unpack",
        mandatory: true,
        result: "passed",
        reason: null,
        finding_summary: null,
        source: "platform_safety_scan",
      },
      {
        schema_version: 1,
        check_id: "path_denylist",
        family: "path",
        mandatory: true,
        result: "failed",
        source: "platform_safety_scan",
        reason: "unsafe_path_detected",
        finding_summary: null,
      },
      {
        schema_version: 1,
        check_id: "secrets_heuristic",
        family: "secrets",
        mandatory: true,
        result: "passed",
        reason: null,
        finding_summary: null,
        source: "platform_safety_scan",
      },
      {
        schema_version: 1,
        check_id: "sast_opengrep",
        family: "sast_generic",
        mandatory: false,
        result: "passed",
        reason: null,
        finding_summary: null,
        source: "platform_safety_scan",
      },
      {
        schema_version: 1,
        check_id: "skill_static_gate",
        family: "skill_static",
        mandatory: true,
        result: "passed",
        reason: null,
        finding_summary: null,
        source: "platform_safety_scan",
      },
    ],
  },
});

export const componentSummary = componentSummaryFixture;

const multiHarnessIds = [
  "antigravity",
  "claude-code",
  "codex",
  "cursor",
  "grok-build",
  "opencode",
  "pi",
] as const;

const multiHarnessSafetyChecks: SafetyCheckEntry[] = [
  {
    schema_version: 1,
    check_id: "artifact_unpack",
    family: "unpack",
    mandatory: true,
    result: "passed",
    reason: null,
    finding_summary: null,
    source: "platform_safety_scan",
  },
  {
    schema_version: 1,
    check_id: "path_denylist",
    family: "path",
    mandatory: true,
    result: "passed",
    reason: null,
    finding_summary: null,
    source: "platform_safety_scan",
  },
];

const multiHarnessTargetMatrix: TargetMatrix = {
  schema_version: 1,
  exact: multiHarnessIds.map((harness_id, index) => ({
    schema_version: 1,
    kind: "exact" as const,
    harness_id,
    adaptation_id: `adaptation_workflow_herdr_${index}`,
    scope: "global" as const,
    implementation_mode: "native" as const,
    projection_kind: "native_files" as const,
    technical_support: "experimental" as const,
    technical_support_reason: "fixture projection",
    supported_os: [],
    supported_arch: [],
    semantic_losses: [],
    permissions_summary: [],
    assessment_state: "verified" as const,
    freshness: FIXTURE_TIMESTAMP,
    recommendation: "ineffective" as const,
    evidence_refs: [],
    safety_checks: multiHarnessSafetyChecks,
  })),
};

export const multiHarnessComponentSummary = makeComponentSummary({
  stable_id: SEED_MULTI_HARNESS_COMPONENT_ID,
  latest_version: "1.3",
  latest_name: "workflow-herdr",
  latest_description: "Fixture skill with one exact projection for every supported harness.",
  latest_harness_id: "antigravity",
  latest_harness_ids: [...multiHarnessIds],
  latest_component_type: "skill",
  latest_projection_kind: "native_files",
  latest_tags: ["herdr", "workflow", "orchestration"],
  latest_published_at: FIXTURE_TIMESTAMP,
  owner_id: FIXTURE_ACCOUNT_ID,
  latest_assurance: { verified_targets: 7, assessed_targets: 7 },
});

export const setupSummaryFixture = makeSetupSummary({
  stable_id: FIXTURE_SETUP_ID,
  latest_version: "1.1",
  latest_name: "python-ci-workspace",
  latest_description:
    "Pinned Claude Code workspace for Python services: security review skill, audit hook, and release checklist.",
  latest_purpose: "Day-to-day development and PR review on Python backends",
  latest_target_role: "backend engineer",
  latest_posture: "baseline",
  latest_harness_id: "claude-code",
  latest_tags: ["python", "tests"],
  latest_published_at: FIXTURE_TIMESTAMP,
  owner_id: FIXTURE_ACCOUNT_ID,
  composition: [pin(FIXTURE_COMPONENT_ID, "1.2")],
});

export const setupSummary = setupSummaryFixture;

export const ALL_COMPONENT_SUMMARIES = [
  componentSummaryFixture,
  multiHarnessComponentSummary,
  ...multiAuthorComponents,
] as const;

export const ALL_SETUP_SUMMARIES = [setupSummaryFixture, ...multiAuthorSetups] as const;

type ComponentDetailFixture = {
  schema_version: 1;
  summary: ComponentSummaryFixture;
  versions: ReturnType<typeof versionEntry>[];
  media: Array<{
    id: string;
    kind: "image";
    url: string;
    alt: string;
    caption: string;
    source_label: string;
  }>;
  target_matrix: TargetMatrix;
};

type SetupDetailFixture = {
  schema_version: 1;
  summary: SetupSummaryFixture;
  versions: ReturnType<typeof versionEntry>[];
  // Per-member checks belong to the detail read. They used to sit inside
  // `summary.latest_checks`, which is also the card `registry search`
  // returns, where the name alone was refused by every released client.
  component_checks: [];
  ported_from: {
    stable_id: string;
    version: string;
    passport_digest: string;
  } | null;
  related_setup_ids: string[];
  family: null;
  composition: [];
};

function componentDetailFrom(
  summary: ComponentSummaryFixture,
  versions: string[] = ["1.0"],
  targetMatrix: TargetMatrix = { schema_version: 1, exact: [] },
): ComponentDetailFixture {
  return {
    schema_version: 1,
    summary,
    media: [
      {
        id: `media_${summary.stable_id}`,
        kind: "image",
        url: `/catalog-art/${summary.latest_component_type}.webp`,
        alt: `${summary.latest_name} preview`,
        caption: "Component preview",
        source_label: "ai_stp signed storage",
      },
    ],
    target_matrix: targetMatrix,
    versions: versions.map((version) =>
      versionEntry(
        version,
        version === summary.latest_version ? summary.latest_published_at : FIXTURE_TIMESTAMP,
        summary.latest_support,
      ),
    ),
  };
}

function setupDetailFrom(
  summary: SetupSummaryFixture,
  versions: string[] = [],
): SetupDetailFixture {
  const offered = versions.length > 0 ? versions : [summary.latest_version];
  return {
    schema_version: 1,
    summary,
    component_checks: [],
    family: null,
    composition: [],
    ported_from:
      summary.stable_id === FIXTURE_SETUP_ID
        ? {
            stable_id: "setup_01JQZK7B8N4M6P2R9T5V0X3YC1",
            version: "1.0",
            passport_digest: ZERO_DIGEST,
          }
        : null,
    related_setup_ids:
      summary.stable_id === FIXTURE_SETUP_ID ? ["setup_01JQZK7B8N4M6P2R9T5V0X3YC2"] : [],
    versions: offered.map((version) =>
      versionEntry(
        version,
        version === summary.latest_version ? summary.latest_published_at : FIXTURE_TIMESTAMP,
        summary.latest_support,
      ),
    ),
  };
}

export const componentDetail = componentDetailFrom(componentSummaryFixture, ["1.0", "1.2"]);
// Two versions, and not as decoration. The machine projection paired the
// heading's `latest_version` with `versions[0]`, which is the *oldest* row —
// wrong for any object with a history and indistinguishable on a fixture with
// one version. The component fixture already carried two, so its half of
// `machine-projection-digest` was a real test; the setup half asserted against a
// single row that could not disagree with itself, and production shipped a page
// naming 1.1 beside 1.0's digest.
export const setupDetail = setupDetailFrom(setupSummaryFixture, ["1.0", "1.1"]);

const componentDetailsEntries: Array<[string, ComponentDetailFixture]> = [
  ...ALL_COMPONENT_SUMMARIES.map((summary): [string, ComponentDetailFixture] => [
    summary.stable_id,
    summary.stable_id === FIXTURE_COMPONENT_ID
      ? componentDetailFrom(summary, ["1.0", "1.2"])
      : componentDetailFrom(summary),
  ]),
  [
    multiHarnessComponentSummary.stable_id,
    componentDetailFrom(multiHarnessComponentSummary, ["1.0", "1.3"], multiHarnessTargetMatrix),
  ],
];

const COMPONENT_DETAILS: Record<string, ComponentDetailFixture> =
  Object.fromEntries(componentDetailsEntries);

const SETUP_DETAILS: Record<string, SetupDetailFixture> = Object.fromEntries(
  ALL_SETUP_SUMMARIES.map((summary) => [summary.stable_id, setupDetailFrom(summary)]),
);

export function getComponentDetail(stableId: string): ComponentDetailFixture | null {
  return COMPONENT_DETAILS[stableId] ?? null;
}

export function getSetupDetail(stableId: string): SetupDetailFixture | null {
  return SETUP_DETAILS[stableId] ?? null;
}

export function getOwnerIdForComponent(stableId: string): string | null {
  return getComponentDetail(stableId)?.summary.owner_id ?? null;
}

export function getOwnerIdForSetup(stableId: string): string | null {
  return getSetupDetail(stableId)?.summary.owner_id ?? null;
}
