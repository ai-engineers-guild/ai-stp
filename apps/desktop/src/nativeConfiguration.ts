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
  restartRequired?: boolean;
  metadataOnly?: boolean;
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
    retirement = record(plan.missing_retirement);
  const metadataOnly =
    retirement.format === "ai-stp-native-missing-target-retirement/1";
  const native = record(
    metadataOnly ? retirement.original_plan : plan.native_plan,
  );
  const context = record(native.context),
    target = record(native.target);
  const operation = plan.operation_id,
    digest = result.data?.plan_digest;
  if (
    typeof operation !== "string" ||
    typeof digest !== "string" ||
    plan.format !== "ai-stp-native-custody-review/1" ||
    native.format !== "ai-stp-native-installation/1" ||
    native.operation_id !==
      (metadataOnly ? retirement.source_operation : operation) ||
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
    metadataOnly,
    stateParent: metadataOnly
      ? originalState({ root: record(retirement.controller).path })
      : originalState(context),
  };
}
export function nativePending(result: CmdResult): NativeOperation | null {
  if (!result.ok) return null;
  const pending = record(result.data?.pending),
    context = record(pending.original_context);
  const operation = pending.operation_id,
    digest = pending.plan_digest,
    phase = record(pending.custody).state ?? "unknown";
  if (
    typeof operation !== "string" ||
    typeof digest !== "string" ||
    typeof phase !== "string" ||
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
    phase,
    metadataOnly: pending.kind === "retire_missing",
    stateParent:
      pending.kind === "retire_missing"
        ? originalState({ root: record(pending.controller).path })
        : originalState(context),
  };
}
/** A completed original operation remains inspectable after an app restart. */
export function nativeStatus(result: CmdResult): NativeOperation | null {
  if (!result.ok) return null;
  const data = record(result.data),
    context = record(data.original_context);
  const receipt = record(data.receipt);
  const operation = data.operation_id,
    digest = data.review_digest;
  if (
    typeof operation !== "string" ||
    typeof digest !== "string" ||
    !id.test(operation) ||
    !hash.test(digest) ||
    receipt.operation_id !== operation ||
    receipt.review_digest !== digest ||
    record(receipt.original_context).context_id !== context.context_id ||
    typeof context.context_id !== "string" ||
    typeof context.label !== "string" ||
    typeof receipt.harness_id !== "string" ||
    (data.state !== "configured" && data.state !== "confirmed") ||
    typeof receipt.restart_required !== "boolean"
  )
    return null;
  return {
    operation,
    digest,
    context: context.context_id,
    label: context.label,
    harness: receipt.harness_id,
    phase: data.state,
    plan: null,
    stateParent: originalState(context),
    restartRequired: receipt.restart_required,
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
    "native",
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
