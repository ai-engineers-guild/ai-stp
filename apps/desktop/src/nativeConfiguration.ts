import { record } from "./contexts";
import type { CmdResult } from "./transport";
export interface NativeOperation {
  operation: string;
  digest: string;
  context: string;
  label: string;
  harness: string;
  plan: Record<string, unknown> | null;
  phase: string;
  stateParent: string | null;
}
function originalState(context: Record<string, unknown>): string | null {
  if (typeof context.root === "string") return context.root;
  const path = record(context.root);
  if (typeof path.utf8_base64 !== "string") return null;
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(
      Uint8Array.from(atob(path.utf8_base64), (c) => c.charCodeAt(0)),
    );
  } catch {
    return null;
  }
}
const id = /^operation_[0-7][0-9A-HJKMNP-TV-Z]{25}$/;
const hash = /^sha256:[0-9a-f]{64}$/;
export function nativeReview(result: CmdResult): NativeOperation | null {
  if (!result.ok) return null;
  const plan = record(result.data?.plan),
    native = record(plan.native_plan);
  const context = record(native.context),
    target = record(native.target);
  const operation = String(plan.operation_id ?? ""),
    digest = String(result.data?.plan_digest ?? "");
  if (
    plan.format !== "ai-stp-native-custody-review/1" ||
    native.format !== "ai-stp-native-installation/1" ||
    native.operation_id !== operation ||
    !id.test(operation) ||
    !hash.test(digest) ||
    typeof context.context_id !== "string" ||
    typeof context.label !== "string" ||
    typeof target.harness_id !== "string"
  )
    return null;
  return {
    operation,
    digest,
    context: context.context_id,
    label: context.label,
    harness: target.harness_id,
    plan,
    phase: "review",
    stateParent: originalState(context),
  };
}
export function nativePending(result: CmdResult): NativeOperation | null {
  if (!result.ok) return null;
  const pending = record(result.data?.pending),
    context = record(pending.original_context);
  const operation = String(pending.operation_id ?? ""),
    digest = String(pending.plan_digest ?? "");
  if (
    !id.test(operation) ||
    !hash.test(digest) ||
    typeof context.context_id !== "string" ||
    typeof context.label !== "string" ||
    typeof pending.harness_id !== "string"
  )
    return null;
  return {
    operation,
    digest,
    context: context.context_id,
    label: context.label,
    harness: pending.harness_id,
    plan: null,
    phase: String(record(pending.custody).state ?? "unknown"),
    stateParent: originalState(context),
  };
}
export function nativeArguments(
  operation: NativeOperation,
): Record<string, string> {
  return { operation: operation.operation, "plan-digest": operation.digest };
}

/** Display/copy only. The app never evaluates the resulting shell text. */
export function confirmationCommand(
  operation: NativeOperation,
  os: string,
): string | null {
  if (!operation.stateParent) return null;
  const args = [
    "ai-stp",
    "configuration",
    "confirm",
    "--operation",
    operation.operation,
    "--plan-digest",
    operation.digest,
    "--state-dir",
    operation.stateParent,
  ];
  const quote = (value: string) =>
    os === "windows"
      ? `'${value.replaceAll("'", "''")}'`
      : `'${value.replaceAll("'", `'\\''`)}'`;
  return `${os === "windows" ? "& " : ""}${args.map(quote).join(" ")}`;
}
