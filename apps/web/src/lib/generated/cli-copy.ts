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
export const COMPONENT_NEXT_STEP = "ai-stp task start --intent author --idempotency-key author-session-01 --json" as const;
export const SETUP_NEXT_STEP = "ai-stp task start --intent install --idempotency-key install-session-01 --json" as const;
export const INSTALL_TASK_START = "ai-stp task start --intent install --idempotency-key {key} --json" as const;
export const INSTALL_SETUP_START = "echo {input} | ai-stp task start --intent install --idempotency-key {key} --input - --json" as const;
export const LOGIN = "ai-stp task start --intent account --idempotency-key account-session-01 --json" as const;
export const INTENTS_BOOTSTRAP = "ai-stp task intents --json" as const;
export const INITIALIZE_START = "ai-stp task start --intent initialize --idempotency-key initialize-session-01 --json" as const;
export const INITIALIZE_PROMPT = "After the CLI is installed, the coding agent runs first-run harness discoverability by executing: ai-stp task start --intent initialize --idempotency-key initialize-session-01 --json" as const;

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
  return SETUP_NEXT_STEP;
}

function installKey(stableId: string, version?: string): string {
  return version ? `install-${stableId}-${version}` : `install-${stableId}`;
}

export function installTaskStart(stableId: string, version?: string): string {
  return INSTALL_TASK_START.replaceAll("{key}", installKey(stableId, version));
}

export function installSetupStart(stableId: string, version: string): string {
  const input = JSON.stringify({ setup_id: stableId, setup_version: version });
  return INSTALL_SETUP_START
    .replaceAll("{input}", `'${input}'`)
    .replaceAll("{key}", installKey(stableId, version));
}

export function login(provider: LoginProvider): string {
  void provider;
  return LOGIN;
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
