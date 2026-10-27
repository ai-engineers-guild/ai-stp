/* Generated from ai_stp_contracts.cli_copy. Do not edit. */

export type ObjectKind = "component" | "setup";
export type LoginProvider = "google" | "github" | "authentik" | "keycloak" | "gitlab" | "saml";

export const DISTRIBUTION = "ai-stp-cli" as const;
export const CLI_RELEASES_URL = "https://github.com/ai-engineers-guild/ai-stp/releases/tag/cli-v0.2.0" as const;
export const REGISTRY_SHOW = "ai-stp registry show --kind {kind} --id {stable_id}" as const;
export const REGISTRY_VERSION =
  "ai-stp registry version --kind {kind} --id {stable_id} --version {version}" as const;
export const SELECT_IMPACT =
  "ai-stp select impact --setup-id {stable_id} --setup-version {version}" as const;
export const COMPONENT_NEXT_STEP = "ai-stp task start --intent author --idempotency-key author-session-01 --json" as const;
export const SETUP_NEXT_STEP = "ai-stp task start --intent author --idempotency-key author-session-01 --json" as const;
export const INSTALL_TASK_START = "Use ai-stp to configure my installed harness with {stable_id}{version_label}. Start with `ai-stp task intents --json`, inspect the exact object and gather the local target, source and provider facts required by the install input schema. Keep harness installation and updates under its own management." as const;
export const INSTALL_SETUP_START = "Use ai-stp to configure my installed harness with {stable_id}{version_label}. Start with `ai-stp task intents --json`, inspect the exact object and gather the local target, source and provider facts required by the install input schema. Keep harness installation and updates under its own management." as const;
export const LOGIN = "ai-stp account plan --action start --provider {provider} --json" as const;
export const INTENTS_BOOTSTRAP = "ai-stp task intents --json" as const;
export const INITIALIZE_START = "ai-stp init --credential-store os_keyring --json" as const;
export const INITIALIZE_PROMPT = "After installing the native CLI, initialize a new local identity with: ai-stp init --credential-store os_keyring --json. Existing Python state requires explicit `ai-stp state migrate plan` and apply." as const;

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

export function installStart(): string {
  return INTENTS_BOOTSTRAP;
}

export function installTaskStart(stableId: string, version?: string): string {
  if (!/^[A-Za-z0-9_]+$/.test(stableId)) throw new Error("invalid catalog object identifier");
  return INSTALL_TASK_START.replaceAll("{stable_id}", stableId)
    .replaceAll("{version_label}", version ? ` version ${version}` : "");
}

export function installSetupStart(stableId: string, version: string): string {
  return installTaskStart(stableId, version);
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
