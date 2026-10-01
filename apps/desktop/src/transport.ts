// Single transport choke point: every backend call goes through `invoke`.
// The reply is a typed CmdResult — ok/data/warnings/continuations/error —
// so the UI never parses stderr or prose.

import { invoke } from "@tauri-apps/api/core";

export interface CliContinuation {
  kind: string;
  path: string[];
  arguments: unknown;
  missing: string[];
  argv: string[];
  actor: "cli" | "human" | "external" | null;
}

export interface CmdResult {
  ok: boolean;
  data: Record<string, unknown> | null;
  warnings: string[];
  continuations: CliContinuation[];
  error: string | null;
  error_code: string | null;
}

export function cmdVersion(): Promise<CmdResult> {
  return invoke<CmdResult>("cli_version");
}

export function cmdCapabilities(): Promise<CmdResult> {
  return invoke<CmdResult>("cli_capabilities");
}

export function cmdDoctor(): Promise<CmdResult> {
  return invoke<CmdResult>("cli_doctor");
}

export function cmdMachineHelp(): Promise<CmdResult> {
  return invoke<CmdResult>("machine_help");
}

export function cmdRunRead(
  path: string,
  values: Record<string, string> = {},
  flags: string[] = [],
): Promise<CmdResult> {
  return invoke<CmdResult>("cli_run_read", { path, values, flags });
}

// -- auth: device-code flow through the CLI; the app holds no credentials.

export function cmdAuthLogin(provider: string): Promise<CmdResult> {
  return invoke<CmdResult>("auth_login", { provider });
}

export function cmdAuthComplete(wait: boolean): Promise<CmdResult> {
  return invoke<CmdResult>("auth_complete", { wait });
}

export function cmdAuthStatus(): Promise<CmdResult> {
  return invoke<CmdResult>("auth_status");
}

export function cmdAuthLogout(): Promise<CmdResult> {
  return invoke<CmdResult>("auth_logout");
}

export function cmdDeviceShow(): Promise<CmdResult> {
  return invoke<CmdResult>("device_show");
}

// -- catalog through the CLI (private acquisition reuses CLI credentials)

export function cmdCatalogSearch(
  kind: string,
  query: string,
  includeExperimental = false,
  cursor?: string,
): Promise<CmdResult> {
  return invoke<CmdResult>("catalog_search", {
    kind,
    query,
    includeExperimental,
    cursor: cursor ?? null,
  });
}

export function cmdCatalogShow(kind: string, stableId: string): Promise<CmdResult> {
  return invoke<CmdResult>("catalog_show", { kind, stableId });
}

// -- tasks (durable journeys)

export function cmdTaskIntents(): Promise<CmdResult> {
  return invoke<CmdResult>("task_intents");
}

export function cmdTaskStart(intent: string): Promise<CmdResult> {
  return invoke<CmdResult>("task_start", { intent });
}

export function cmdTaskStatus(taskId: string): Promise<CmdResult> {
  return invoke<CmdResult>("task_status", { taskId });
}

export function cmdTaskList(): Promise<CmdResult> {
  return invoke<CmdResult>("task_list");
}
