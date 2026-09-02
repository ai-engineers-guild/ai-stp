/**
 * Version passport projections for mock catalog reads (REQ-2207).
 */
import {
  experimentalTrust,
  getComponentDetail,
  getOwnerIdForComponent,
  getOwnerIdForSetup,
  getSetupDetail,
  FIXTURE_ACCOUNT_ID,
  FIXTURE_TIMESTAMP,
  ZERO_DIGEST,
} from "./fixtures";

const EMPTY_CONFLICTS = {
  paths: [] as string[],
  commands: [] as string[],
  hooks: [] as string[],
  mcp: [] as string[],
  agents: [] as string[],
  plugins: [] as string[],
};

type ComponentPassportInput = {
  stableId: string;
  name: string;
  description: string;
  version: string;
  tags: string[];
  harnessId: string;
  componentType: string;
  projectionKind?: string;
  publishedAt?: string;
  ownerId?: string;
};

export function buildComponentPassport(input: ComponentPassportInput) {
  return {
    schema_version: 1 as const,
    kind: "component" as const,
    stable_id: input.stableId,
    revision_id: "revision_9f90ce539ce28826fef5fbb669a1566ae8d6b4a57018611f9ef85eded3ab36cc",
    parent_revision_ids: [] as string[],
    owner_id: input.ownerId ?? FIXTURE_ACCOUNT_ID,
    created_at: input.publishedAt ?? FIXTURE_TIMESTAMP,
    visibility: "public" as const,
    facts: {},
    name: input.name,
    description: input.description,
    version: input.version,
    tags: input.tags,
    source: {
      repository: `https://github.com/ai-stp-examples/${input.name}`,
      commit: "6f1b0f5f7f3f4f2a1c9d8e7b6a5f4e3d2c1b0a99",
      path: `components/${input.name}`,
    },
    artifact: { digest: ZERO_DIGEST, size_bytes: 1024 },
    harness_id: input.harnessId,
    required_env: [] as { name: string; purpose: string }[],
    requires_credentials: false,
    requires_authorization: "none" as const,
    permissions: { filesystem: [] as string[], network: [] as string[], process: [] as string[] },
    external_endpoints: [] as string[],
    license: { spdx_id: "AGPL-3.0-or-later", redistribution_allowed: true },
    compatibility_evidence_refs: [] as string[],
    component_type: input.componentType,
    projection_kind: input.projectionKind ?? "native_files",
    variant_id: null,
    provides_capabilities: [] as string[],
    requires_components: [] as {
      stable_id: string;
      version: string;
      passport_digest: string;
      variant_id?: string | null;
    }[],
    requires_capabilities: [] as string[],
    conflicts: EMPTY_CONFLICTS,
    managed_paths: [] as string[],
    native_ids: [] as string[],
    harness_ids: [input.harnessId] as string[],
    supported_os: ["linux", "macos"] as Array<"linux" | "macos" | "windows">,
  };
}

type SetupPassportInput = {
  stableId: string;
  name: string;
  description: string;
  version: string;
  tags: string[];
  harnessId: string;
  purpose: string;
  targetRole: string | null;
  components: {
    stable_id: string;
    version: string;
    passport_digest: string;
    variant_id?: string | null;
  }[];
  publishedAt?: string;
  supportedTasks?: string[];
  ownerId?: string;
};

export function buildSetupPassport(input: SetupPassportInput) {
  return {
    schema_version: 1 as const,
    kind: "setup" as const,
    stable_id: input.stableId,
    revision_id: "revision_17c0933d0091430a6750bddf86e03277cd06675b7520a340f75cd30a439c7045",
    parent_revision_ids: [] as string[],
    owner_id: input.ownerId ?? FIXTURE_ACCOUNT_ID,
    created_at: input.publishedAt ?? FIXTURE_TIMESTAMP,
    visibility: "public" as const,
    facts: {},
    name: input.name,
    description: input.description,
    version: input.version,
    tags: input.tags,
    source: null,
    artifact: { digest: ZERO_DIGEST, size_bytes: 2048 },
    harness_id: input.harnessId,
    required_env: [] as { name: string; purpose: string }[],
    requires_credentials: false,
    requires_authorization: "none" as const,
    permissions: { filesystem: [] as string[], network: [] as string[], process: [] as string[] },
    external_endpoints: [] as string[],
    license: { spdx_id: "AGPL-3.0-or-later", redistribution_allowed: true },
    compatibility_evidence_refs: [] as string[],
    purpose: input.purpose,
    target_role: input.targetRole,
    posture: "baseline" as string | null,
    supported_tasks: input.supportedTasks ?? ["development"],
    components: input.components,
    ported_from: null,
    related_setup_ids: [] as string[],
    execution_profile: "full-auto" as const,
    supported_harness_versions: ["2.1.0"],
    supported_os: ["linux"] as Array<"linux" | "macos" | "windows">,
    supported_arch: ["x86_64"] as ("x86_64" | "arm64")[],
    composition_report_ref: null,
    conversion_report_ref: null,
    install_evidence_ref: null,
    launch_evidence_ref: null,
  };
}

export function componentVersionResponse(stableId: string, version: string) {
  const detail = getComponentDetail(stableId);
  if (!detail) {
    return null;
  }
  const summary = detail.summary;
  return {
    schema_version: 1 as const,
    passport: buildComponentPassport({
      stableId,
      name: summary.latest_name,
      description: summary.latest_description,
      version,
      tags: [...summary.latest_tags],
      harnessId: summary.latest_harness_id,
      componentType: summary.latest_component_type,
      projectionKind: summary.latest_projection_kind,
      publishedAt: summary.latest_published_at,
      ownerId: getOwnerIdForComponent(stableId) ?? FIXTURE_ACCOUNT_ID,
    }),
    passport_digest: ZERO_DIGEST,
    lifecycle: "active" as const,
    trust: experimentalTrust,
    support: summary.latest_support,
    published_at: summary.latest_published_at,
  };
}

export function setupVersionResponse(stableId: string, version: string) {
  const detail = getSetupDetail(stableId);
  if (!detail) {
    return null;
  }
  const summary = detail.summary;
  return {
    schema_version: 1 as const,
    passport: buildSetupPassport({
      stableId,
      name: summary.latest_name,
      description: summary.latest_description,
      version,
      tags: [...summary.latest_tags],
      harnessId: summary.latest_harness_id,
      purpose: summary.latest_purpose,
      targetRole: summary.latest_target_role,
      components: summary.composition.map((item) => ({ ...item })),
      publishedAt: summary.latest_published_at,
      ownerId: getOwnerIdForSetup(stableId) ?? FIXTURE_ACCOUNT_ID,
    }),
    passport_digest: ZERO_DIGEST,
    lifecycle: "active" as const,
    trust: experimentalTrust,
    support: summary.latest_support,
    published_at: summary.latest_published_at,
    // A version read is a detail read, so it carries the per-member checks
    // that the card deliberately does not.
    component_checks: [],
  };
}
