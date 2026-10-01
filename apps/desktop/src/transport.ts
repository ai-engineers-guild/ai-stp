// Single transport choke point: every backend call goes through `invoke`.
// The reply is a typed CmdResult — ok/data/warnings/continuations/error —
// so the UI never parses stderr or prose.

import { invoke } from "@tauri-apps/api/core";
import { redact } from "./redact";
import { useDebug } from "./store";

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

/** Every call goes through here: the Debug page logs cmd, args, latency,
 *  ok and error_code for diagnostics. Results are kept on the entry so a
 *  failure can be inspected without re-running the command. */
function call(command: string, args?: Record<string, unknown>): Promise<CmdResult> {
  const t0 = performance.now();
  const argsRec = args ?? {};
  return invoke<CmdResult>(command, argsRec).then(
    (r) => {
      useDebug.getState().push({
        cmd: command, args: argsRec, ms: Math.round(performance.now() - t0),
        ok: r.ok, error_code: r.error_code, error: r.error,
        result: redact(r) as CmdResult,
      });
      return r;
    },
    (e) => {
      useDebug.getState().push({
        cmd: command, args: argsRec, ms: Math.round(performance.now() - t0),
        ok: null, error_code: "IPC_THROW", error: String(e),
      });
      throw e;
    },
  );
}

export function cmdVersion(): Promise<CmdResult> {
  return call("cli_version");
}

export function cmdCapabilities(): Promise<CmdResult> {
  return call("cli_capabilities");
}

export function cmdDebugInfo(): Promise<CmdResult> {
  return call("debug_info");
}

export function cmdDoctor(): Promise<CmdResult> {
  return call("cli_doctor");
}

export function cmdMachineHelp(): Promise<CmdResult> {
  return call("machine_help");
}

export function cmdRunRead(
  path: string,
  values: Record<string, string> = {},
  flags: string[] = [],
): Promise<CmdResult> {
  return call("cli_run_read", { path, values, flags });
}

// -- auth: device-code flow through the CLI; the app holds no credentials.

export function cmdAuthLogin(provider: string): Promise<CmdResult> {
  return call("auth_login", { provider });
}

export function cmdAuthComplete(wait: boolean): Promise<CmdResult> {
  return call("auth_complete", { wait });
}

export function cmdAuthStatus(): Promise<CmdResult> {
  return call("auth_status");
}

export function cmdAuthLogout(): Promise<CmdResult> {
  return call("auth_logout");
}

export function cmdDeviceShow(): Promise<CmdResult> {
  return call("device_show");
}

// -- catalog through the CLI (private acquisition reuses CLI credentials)

export function cmdCatalogSearch(
  kind: string,
  query: string,
  includeExperimental = false,
  cursor?: string,
): Promise<CmdResult> {
  return call("catalog_search", {
    kind,
    query,
    includeExperimental,
    cursor: cursor ?? null,
  });
}

export function cmdCatalogShow(kind: string, stableId: string): Promise<CmdResult> {
  return call("catalog_show", { kind, stableId });
}

// -- install: plan → digest confirm → apply, all through descriptor-built argv

export function cliPlan(
  path: string,
  values: Record<string, string>,
  flags: string[] = [],
): Promise<CmdResult> {
  return call("cli_plan", { path, values, flags });
}

export function cliApplyConfirmed(
  path: string,
  values: Record<string, string>,
  flags: string[] = [],
  confirmed = false,
): Promise<CmdResult> {
  return call("cli_apply_confirmed", { path, values, flags, confirmed });
}

// -- tasks (durable journeys)

export function cmdTaskIntents(): Promise<CmdResult> {
  return call("task_intents");
}

export function cmdTaskStart(intent: string): Promise<CmdResult> {
  return call("task_start", { intent });
}

export function cmdTaskStatus(taskId: string): Promise<CmdResult> {
  return call("task_status", { taskId });
}

export function cmdTaskAnswer(
  task: string,
  revision: string,
  questionId: string,
  value: string,
): Promise<CmdResult> {
  return call("task_answer", { task, revision, questionId, value });
}

export function cmdTaskContinue(task: string, revision: string): Promise<CmdResult> {
  return call("task_continue", { task, revision });
}

export function cmdTaskCancel(task: string, revision: string): Promise<CmdResult> {
  return call("task_cancel", { task, revision });
}

export function cmdTaskList(): Promise<CmdResult> {
  return call("task_list");
}
