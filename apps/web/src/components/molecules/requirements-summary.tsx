import type { ComponentRef, EnvVarRequirement, Permissions } from "@/lib/api/generated/types.gen";
import { DetailAccordion } from "@/components/molecules/detail-accordion";

export type Requirements = {
  required_env: EnvVarRequirement[];
  requires_credentials: boolean;
  requires_authorization: "none" | "user_account" | "external_service";
  permissions: Permissions;
  external_endpoints: string[];
  requires_components?: ComponentRef[];
  requires_capabilities?: string[];
  supported_harness_versions?: string[];
  supported_os?: string[];
  supported_arch?: string[];
  harness_ids?: string[];
  runtime_requirements?: string[];
};

export function mergeRequirements(items: Requirements[]): Requirements {
  const authorization = items.some((item) => item.requires_authorization === "external_service")
    ? "external_service"
    : items.some((item) => item.requires_authorization === "user_account")
      ? "user_account"
      : "none";
  return {
    required_env: Array.from(
      new Map(items.flatMap((item) => item.required_env).map((item) => [item.name, item])).values(),
    ),
    requires_credentials: items.some((item) => item.requires_credentials),
    requires_authorization: authorization,
    permissions: {
      filesystem: [...new Set(items.flatMap((item) => item.permissions.filesystem ?? []))],
      network: [...new Set(items.flatMap((item) => item.permissions.network ?? []))],
      process: [...new Set(items.flatMap((item) => item.permissions.process ?? []))],
    },
    external_endpoints: [...new Set(items.flatMap((item) => item.external_endpoints))],
    requires_components: Array.from(
      new Map(
        items
          .flatMap((item) => item.requires_components ?? [])
          .map((item) => [`${item.stable_id}@${item.version}`, item]),
      ).values(),
    ),
    requires_capabilities: [...new Set(items.flatMap((item) => item.requires_capabilities ?? []))],
    supported_harness_versions: [
      ...new Set(items.flatMap((item) => item.supported_harness_versions ?? [])),
    ],
    supported_os: [...new Set(items.flatMap((item) => item.supported_os ?? []))],
    supported_arch: [...new Set(items.flatMap((item) => item.supported_arch ?? []))],
    harness_ids: [...new Set(items.flatMap((item) => item.harness_ids ?? []))],
    runtime_requirements: [...new Set(items.flatMap((item) => item.runtime_requirements ?? []))],
  };
}
export type RequirementsLabels = {
  title: string;
  credentials: string;
  authorization: string;
  environment: string;
  permissions: string;
  endpoints: string;
  components: string;
  capabilities: string;
  harnessVersions: string;
  operatingSystems: string;
  architectures: string;
  harnesses: string;
  runtime: string;
  none: string;
  yes: string;
  no: string;
};

export function requirementLabels(
  t: (key: string) => string,
  tc: (key: string) => string,
): RequirementsLabels {
  return {
    title: t("requirements"),
    credentials: t("requiresCredentials"),
    authorization: t("requiresAuthorization"),
    environment: t("requiredEnvironment"),
    permissions: t("permissions"),
    endpoints: t("externalEndpoints"),
    components: t("requiredComponents"),
    capabilities: t("requiredCapabilities"),
    harnessVersions: t("supportedHarnessVersions"),
    operatingSystems: t("supportedOs"),
    architectures: t("supportedArch"),
    harnesses: t("supportedHarnesses"),
    runtime: t("runtimeRequirements"),
    none: t("noneListed"),
    yes: tc("yes"),
    no: tc("no"),
  };
}

export function RequirementsSummary({
  requirements,
  labels,
}: {
  requirements: Requirements;
  labels: RequirementsLabels;
}) {
  const permissions = [
    ...(requirements.permissions.filesystem ?? []).map((value) => `filesystem: ${value}`),
    ...(requirements.permissions.network ?? []).map((value) => `network: ${value}`),
    ...(requirements.permissions.process ?? []).map((value) => `process: ${value}`),
  ];
  const groups = [
    {
      label: labels.credentials,
      values: [requirements.requires_credentials ? labels.yes : labels.no],
    },
    { label: labels.authorization, values: [requirements.requires_authorization] },
    {
      label: labels.environment,
      values: requirements.required_env.map((item) => `${item.name} — ${item.purpose}`),
    },
    {
      label: labels.components,
      values: (requirements.requires_components ?? []).map(
        (item) => `${item.stable_id}@${item.version}`,
      ),
    },
    { label: labels.capabilities, values: requirements.requires_capabilities ?? [] },
    { label: labels.harnessVersions, values: requirements.supported_harness_versions ?? [] },
    { label: labels.operatingSystems, values: requirements.supported_os ?? [] },
    { label: labels.architectures, values: requirements.supported_arch ?? [] },
    { label: labels.harnesses, values: requirements.harness_ids ?? [] },
    { label: labels.runtime, values: requirements.runtime_requirements ?? [] },
    { label: labels.permissions, values: permissions, mono: true },
    { label: labels.endpoints, values: requirements.external_endpoints, mono: true },
  ];
  return (
    <DetailAccordion
      title={labels.title}
      summary={`${countRequirements(requirements)} · ${labels.credentials}: ${requirements.requires_credentials ? labels.yes : labels.no}`}
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {groups.map((group) => (
          <RequirementList key={group.label} {...group} empty={labels.none} />
        ))}
      </div>
    </DetailAccordion>
  );
}

function countRequirements(requirements: Requirements): number {
  return (
    requirements.required_env.length +
    (requirements.requires_components?.length ?? 0) +
    (requirements.requires_capabilities?.length ?? 0) +
    (requirements.runtime_requirements?.length ?? 0) +
    (requirements.harness_ids?.length ?? 0) +
    Object.values(requirements.permissions).flat().length +
    requirements.external_endpoints.length
  );
}

function RequirementList({
  label,
  values,
  empty,
  mono = false,
}: {
  label: string;
  values: string[];
  empty: string;
  mono?: boolean;
}) {
  return (
    <div className="bg-muted/30 min-w-0 rounded-sm p-3">
      <h3 className="text-sm font-semibold">{label}</h3>
      {values.length ? (
        <ul className="mt-1.5 space-y-1 text-sm leading-5">
          {values.map((value, index) => (
            <li
              key={`${value}-${index}`}
              className={mono ? "font-mono text-xs break-all" : "break-words"}
            >
              {value}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground mt-1.5 text-sm">{empty}</p>
      )}
    </div>
  );
}
