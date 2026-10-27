import { record, type ContextView } from "./contexts";
import { checkoutPath, retainedCheckout } from "./checkoutLinks";
import type { CmdResult } from "./transport";

export interface BindingRetirementReview {
  plan: Record<string, unknown>;
  digest: string;
}

function anchored(plan: Record<string, unknown>, original: Record<string, unknown>): boolean {
  const source = retainedCheckout(original);
  if (!source || source.action !== "adopt" || original.state !== "completed") return false;
  const before = record(record(source.plan.change).snapshot),
    snapshot = record(plan.snapshot), binding = record(snapshot.binding),
    account = record(snapshot.account), heldAccount = record(before.account),
    local = record(before.local_project), root = record(local.root),
    link = record(record(original.effect).link), cached = record(binding.link),
    remote = record(snapshot.remote_link);
  const expectedRoot = checkoutPath(root.path);
  const coordinates = ["link_id", "organization_id", "local_project_id", "remote_project_id", "provider_project_id", "plan_id", "plan_digest"];
  return plan.schema_version === 1 && plan.registry_schema_after === 60 &&
    typeof plan.registry_schema_before === "number" && [57, 58, 59, 60].includes(plan.registry_schema_before) &&
    typeof plan.operation_id === "string" && plan.operation_id !== source.plan.operation_id &&
    checkoutPath(plan.state_parent) !== null && checkoutPath(plan.state_parent) === checkoutPath(source.plan.state_parent) &&
    record(binding.source).operation_id === source.plan.operation_id &&
    record(binding.source).plan_digest === source.digest &&
    record(binding.request).operation_id === record(source.plan.change).request_operation_id &&
    typeof heldAccount.account_id === "string" && account.account_id === heldAccount.account_id &&
    typeof heldAccount.origin === "string" && account.origin === heldAccount.origin &&
    record(snapshot.organization).organization_id === record(before.organization).organization_id &&
    expectedRoot !== null && checkoutPath(binding.checkout_root) === expectedRoot &&
    Array.isArray(root.identity) && root.identity.length === 2 &&
    JSON.stringify(binding.physical_root) === JSON.stringify(root.identity) &&
    record(binding.local_project).stable_id === local.local_project_id &&
    typeof link.link_id === "string" && typeof link.plan_id === "string" &&
    typeof link.plan_digest === "string" &&
    coordinates.every((field) => field in link && cached[field] === link[field] && remote[field] === link[field]) &&
    remote.state === "unlinked" && Number.isSafeInteger(remote.revision) &&
    Number.isSafeInteger(cached.revision) && Number(remote.revision) > Number(cached.revision);
}

export function bindingRetirementReview(
  response: CmdResult,
  context: ContextView,
  original: Record<string, unknown>,
): BindingRetirementReview | null {
  const plan = record(response.data?.plan), snapshot = record(plan.snapshot), account = record(snapshot.account);
  const digest = response.data?.plan_digest;
  if (!response.ok || typeof digest !== "string" || !/^sha256:[0-9a-f]{64}$/.test(digest) ||
    !anchored(plan, original) || context.mode !== "corporate" ||
    record(snapshot.context).context_id !== context.id || account.origin !== context.origin ||
    (record(account.connection).connection_id ?? null) !== context.connection) return null;
  return { plan, digest };
}

export function bindingRetirementReceipt(value: unknown, original: Record<string, unknown>): boolean {
  const receipt = record(value), plan = record(receipt.plan), binding = record(record(plan.snapshot).binding);
  return anchored(plan, original) && typeof receipt.plan_digest === "string" &&
    /^sha256:[0-9a-f]{64}$/.test(receipt.plan_digest) && receipt.operation_id === plan.operation_id &&
    receipt.state === "verified" && receipt.outcome === "local_binding_retired" &&
    receipt.binding_operation_id === record(binding.source).operation_id &&
    receipt.original_request_operation_id === record(binding.request).operation_id &&
    receipt.local_binding_retired === true && receipt.reservation_released === true &&
    receipt.remote_write_submitted === false && receipt.harness_files_changed === false &&
    receipt.tasks_changed === false && receipt.installation_authority === false;
}
