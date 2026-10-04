// Single transport choke point: every backend call goes through `invoke`.
// The reply is a typed CmdResult — ok/data/warnings/continuations/error —
// so the UI never parses stderr or prose.

import { invoke } from "@tauri-apps/api/core";
import { redact } from "./redact";
import { useDebug, type IpcEntry } from "./store";

export interface CliContinuation {
  kind: string;
  path: string[];
  arguments: unknown;
  missing: string[];
  argv: string[];
  actor: "cli" | "human" | "external" | "agent" | null;
}

export interface CmdResult {
  ok: boolean;
  data: Record<string, unknown> | null;
  warnings: string[];
  continuations: CliContinuation[];
  error: string | null;
  error_code: string | null;
  // `error.details` verbatim — `details.options` is the contract's
  // one-retry repair channel for parse/selector failures (cli-json.md).
  error_details?: Record<string, unknown> | null;
  request_id?: string | null;
  operation_id?: string | null;
  error_retryable?: boolean | null;
  next_actions?: unknown[];
}

/** Every call goes through here: the Debug page logs cmd, args, latency,
 *  ok and error_code for diagnostics. Results are kept on the entry so a
 *  failure can be inspected without re-running the command.
 *
 *  Never rejects: an IPC-level failure (handler panic, killed sidecar)
 *  becomes a `CmdResult` with error_code "IPC_THROW" so callers always
 *  get a renderable result — a thrown invoke would otherwise strand
 *  busy/spinner state forever on the calling page. */
function call(command: string, args?: Record<string, unknown>): Promise<CmdResult> {
  const t0 = performance.now();
  const argsRec = args ?? {};
  // args go through redact like results — plus `task answer`'s `value`,
  // which is free user text the debug bundle would otherwise carry
  // verbatim; key-name redaction cannot see it, so it is named here.
  const tracedArgs =
    command === "task_answer" && "value" in argsRec
      ? { ...(redact(argsRec) as Record<string, unknown>), value: "[user answer]" }
      : (redact(argsRec) as Record<string, unknown>);
  const trace = (e: Omit<IpcEntry, "id" | "ts">) => {
    if (useDebug.getState().debugMode) useDebug.getState().push(e);
  };
  return invoke<CmdResult>(command, argsRec).then(
    (r) => {
      trace({
        cmd: command, args: tracedArgs,
        ms: Math.round(performance.now() - t0),
        ok: r.ok, error_code: r.error_code, error: r.error,
        result: redact(r) as CmdResult,
      });
      return r;
    },
    (e) => {
      trace({
        cmd: command, args: tracedArgs,
        ms: Math.round(performance.now() - t0),
        ok: null, error_code: "IPC_THROW", error: String(e),
      });
      return {
        ok: false, data: null, warnings: [], continuations: [],
        error: `IPC call failed: ${String(e)}`, error_code: "IPC_THROW",
      };
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

interface WireParameter {
  name?: string;
  choices?: string[];
}

interface WireDescriptor {
  path?: string[];
  parameters?: WireParameter[];
}

/** The `choices` the CLI publishes for `path`'s `param`, or `null` when the
 *  machine help cannot answer — the caller's fallback is its business. */
export function descriptorChoices(
  help: CmdResult | null,
  path: string,
  param: string,
): string[] | null {
  const commands = (help?.data?.commands as WireDescriptor[] | undefined) ?? [];
  const choices = commands
    .find((d) => (d.path ?? []).join(" ") === path)
    ?.parameters?.find((p) => p.name === param)?.choices;
  return choices && choices.length > 0 ? choices : null;
}

export function cmdRunRead(
  path: string,
  values: Record<string, string> = {},
  flags: string[] = [],
  repeated: Record<string, string[]> = {},
): Promise<CmdResult> {
  return call("cli_run_read", { path, values, flags, repeated });
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
  repeated: Record<string, string[]> = {},
): Promise<CmdResult> {
  return call("cli_plan", { path, values, flags, repeated });
}

export function cliApplyConfirmed(
  path: string,
  values: Record<string, string>,
  flags: string[] = [],
  confirmed = false,
  repeated: Record<string, string[]> = {},
): Promise<CmdResult> {
  return call("cli_apply_confirmed", { path, values, flags, confirmed, repeated });
}

// -- tasks (durable journeys)

export function cmdTaskIntents(): Promise<CmdResult> {
  return call("task_intents");
}

export function cmdTaskStart(
  intent: string,
  idemKey?: string,
): Promise<CmdResult> {
  // One key per logical start: a timeout-and-retry hits the CLI's
  // idempotency dedup instead of forking a duplicate task. `task start
  // --input` is a file path on the CLI, not an inline blob — it is not
  // exposed here (answers go through `task answer`).
  return call("task_start", {
    intent,
    idemKey: idemKey ?? null,
  });
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
