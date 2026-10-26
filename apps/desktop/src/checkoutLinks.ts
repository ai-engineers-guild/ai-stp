import { record, type ContextView } from "./contexts";
import type { CmdResult } from "./transport";

export type CheckoutAction = "request" | "confirm" | "adopt";
export interface CheckoutReview {
  action: CheckoutAction;
  plan: Record<string, unknown>;
  digest: string;
}

/** Decode the CLI's byte-preserving LocalPath; display text cannot reopen it. */
export function checkoutPath(value: unknown): string | null {
  const path = record(value);
  if (Object.keys(path).length !== 2 || typeof path.display !== "string" ||
    typeof path.utf8_base64 !== "string" || path.utf8_base64.length > 43692) return null;
  try {
    const binary = atob(path.utf8_base64);
    if (!binary.length || binary.length > 32768 || btoa(binary) !== path.utf8_base64) return null;
    const decoded = new TextDecoder("utf-8", { fatal: true }).decode(
      Uint8Array.from(binary, (character) => character.charCodeAt(0)),
    );
    if (decoded.includes("\0") || decoded.normalize("NFC") !== path.display ||
      !(decoded.startsWith("/") || /^[A-Za-z]:[\\/]/.test(decoded) || decoded.startsWith("\\\\"))) return null;
    return decoded;
  } catch { return null; }
}

export function checkoutFailure(): CmdResult {
  return {
    ok: false,
    data: null,
    error: "The checkout reply differs from the exact reviewed company operation. Read its original journal in Activity.",
    error_code: "CONTEXT_VIEW",
    warnings: [],
    continuations: [],
  };
}

export function checkoutReview(
  response: CmdResult,
  action: CheckoutAction,
  context: ContextView,
  project: string,
  anchor: Record<string, unknown>,
  request?: string,
): CheckoutReview | null {
  const plan = record(response.data?.plan),
    change = record(plan.change),
    snapshot = record(change.snapshot),
    account = record(snapshot.account),
    original = record(anchor.account),
    local = record(snapshot.local_project),
    expectedLocal = record(anchor.local_project),
    organization = record(snapshot.organization);
  const digest = response.data?.plan_digest;
  const expectedRoot = checkoutPath(record(expectedLocal.root).path);
  if (
    !response.ok || typeof digest !== "string" ||
    !/^sha256:[0-9a-f]{64}$/.test(digest) ||
    typeof plan.operation_id !== "string" || change.action !== action ||
    typeof original.account_id !== "string" ||
    typeof record(anchor.organization).organization_id !== "string" ||
    typeof expectedLocal.local_project_id !== "string" ||
    expectedRoot === null ||
    !Array.isArray(record(expectedLocal.root).identity) ||
    (record(expectedLocal.root).identity as unknown[]).length !== 2 ||
    record(snapshot.context).context_id !== context.id ||
    account.origin !== context.origin || account.account_id !== original.account_id ||
    (record(account.connection).connection_id ?? null) !== context.connection ||
    organization.organization_id !== record(anchor.organization).organization_id ||
    record(snapshot.target).remote_project_id !== project ||
    local.local_project_id !== expectedLocal.local_project_id ||
    checkoutPath(plan.checkout_root) !== expectedRoot ||
    checkoutPath(record(local.root).path) !== expectedRoot ||
    JSON.stringify(record(local.root).identity) !== JSON.stringify(record(expectedLocal.root).identity) ||
    record(snapshot.request_coordinates).provider_project_id !== record(anchor.request_coordinates).provider_project_id ||
    (action !== "request" && change.request_operation_id !== request)
  ) return null;
  return { action, plan, digest };
}

export function checkoutReceipt(response: CmdResult, review: CheckoutReview): boolean {
  const data = record(response.data), effect = record(data.effect);
  return response.ok && data.operation_id === review.plan.operation_id &&
    data.plan_digest === review.digest && data.installation_authority === false &&
    data.state === "completed" && effect.effect === {
      request: "requested", confirm: "confirmed", adopt: "adopted",
    }[review.action];
}

export function retainedCheckout(value: unknown): CheckoutReview | null {
  const data = record(value), plan = record(data.plan), action = record(plan.change).action;
  if (typeof data.operation_id !== "string" || data.operation_id !== plan.operation_id ||
    typeof data.plan_digest !== "string" || !/^sha256:[0-9a-f]{64}$/.test(data.plan_digest) ||
    !["request", "confirm", "adopt"].includes(String(action)) ||
    !["applying", "interrupted", "completed", "retired"].includes(String(data.state)) ||
    data.installation_authority !== false || checkoutPath(plan.checkout_root) === null) return null;
  const snapshot = record(record(plan.change).snapshot);
  if (typeof record(snapshot.context).context_id !== "string" ||
    typeof record(snapshot.account).origin !== "string" ||
    typeof record(snapshot.account).account_id !== "string" ||
    typeof record(snapshot.organization).organization_id !== "string" ||
    typeof record(snapshot.target).remote_project_id !== "string") return null;
  return { action: action as CheckoutAction, plan, digest: data.plan_digest };
}

export function checkoutReader(context: ContextView | null, contexts: CmdResult | null, review: CheckoutReview): string | undefined {
  if (!context || context.mode !== "corporate" || !contexts?.ok) return undefined;
  const rows = contexts.data?.contexts;
  if (!Array.isArray(rows)) return undefined;
  const saved = record(record(rows.find((row) => record(record(row).context).context_id === context.id)).context);
  const authority = record(saved.authority), account = record(authority.account);
  const original = record(record(review.plan.change).snapshot);
  return authority.kind === "remote" &&
    account.origin === context.origin &&
    typeof account.account_id === "string" &&
    typeof record(authority.organization).organization_id === "string" &&
    account.origin === record(original.account).origin &&
    account.account_id === record(original.account).account_id &&
    record(authority.organization).organization_id === record(original.organization).organization_id
    ? context.id : undefined;
}
