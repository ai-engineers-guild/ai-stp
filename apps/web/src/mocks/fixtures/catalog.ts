import { FIXTURE_ACCOUNT_ID, FIXTURE_TIMESTAMP } from "./identity";
import {
  FIXTURE_COMPONENT_ID,
  FIXTURE_SETUP_ID,
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

export const ALL_COMPONENT_SUMMARIES = [componentSummaryFixture, ...multiAuthorComponents] as const;

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
};

type SetupDetailFixture = {
  schema_version: 1;
  summary: SetupSummaryFixture;
  versions: ReturnType<typeof versionEntry>[];
};

function componentDetailFrom(
  summary: ComponentSummaryFixture,
  versions: string[] = ["1.0"],
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

const COMPONENT_DETAILS: Record<string, ComponentDetailFixture> = Object.fromEntries(
  ALL_COMPONENT_SUMMARIES.map((summary) => [
    summary.stable_id,
    summary.stable_id === FIXTURE_COMPONENT_ID
      ? componentDetailFrom(summary, ["1.0", "1.2"])
      : componentDetailFrom(summary),
  ]),
);

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
