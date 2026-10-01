// Single transport choke point (HK pattern adapted): every backend call goes
// through `invoke`. The reply is a typed CmdResult — ok/data/warnings/
// continuations/error — so the UI never parses stderr or prose.

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

export function cmdAuthStatus(): Promise<CmdResult> {
  return invoke<CmdResult>("cli_auth_status");
}
