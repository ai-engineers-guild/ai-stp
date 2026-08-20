/* Generated from ai_stp_contracts.cli_copy. Do not edit. */

export type ObjectKind = "component" | "setup";
export type LoginProvider = "google" | "github";

export const DISTRIBUTION = "ai-stp-cli" as const;
export const INSTALL_CLI = "uv tool install ai-stp-cli" as const;
export const REGISTRY_SHOW = "ai-stp registry show --kind {kind} --id {stable_id}" as const;
export const REGISTRY_VERSION =
  "ai-stp registry version --kind {kind} --id {stable_id} --version {version}" as const;
export const SELECT_IMPACT =
  "ai-stp select impact --setup-id {stable_id} --setup-version {version}" as const;
export const COMPONENT_NEXT_STEP = "ai-stp component discover" as const;
export const SETUP_NEXT_STEP = "ai-stp toolchain harnesses" as const;
export const LOGIN = "ai-stp auth login --provider {provider}" as const;

export function registryShow(kind: ObjectKind, stableId: string): string {
  return REGISTRY_SHOW.replaceAll("{kind}", kind).replaceAll("{stable_id}", stableId);
}

export function registryVersion(kind: ObjectKind, stableId: string, version: string): string {
  return REGISTRY_VERSION.replaceAll("{kind}", kind)
    .replaceAll("{stable_id}", stableId)
    .replaceAll("{version}", version);
}

export function selectImpact(stableId: string, version: string): string {
  return SELECT_IMPACT.replaceAll("{stable_id}", stableId)
    .replaceAll("{version}", version);
}

export function ownerComponentNextStep(): string {
  return COMPONENT_NEXT_STEP;
}

export function ownerSetupNextStep(): string {
  return SETUP_NEXT_STEP;
}

export function login(provider: LoginProvider): string {
  return LOGIN.replaceAll("{provider}", provider);
}

export function objectKindFromId(stableId: string): ObjectKind {
  if (stableId.startsWith("setup_")) {
    return "setup";
  }
  return "component";
}

export function registryCommand(stableId: string, version?: string): string {
  const kind = objectKindFromId(stableId);
  if (version) {
    return registryVersion(kind, stableId, version);
  }
  return registryShow(kind, stableId);
}
