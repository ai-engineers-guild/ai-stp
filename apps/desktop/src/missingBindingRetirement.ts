import { record, type ContextView } from "./contexts";
import { checkoutPath } from "./checkoutLinks";
import { locationPhysical } from "./checkoutLocation";
import { bindingRetirementAnchored, type BindingRetirementReview } from "./bindingRetirement";
import type { CmdResult } from "./transport";

const kind = "corporate.project_binding.retire_missing";
const hash = (value: unknown): value is string => typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);
const keys = (value: Record<string, unknown>, names: string) => Object.keys(value).sort().join(",") === names;

function anchored(plan: Record<string, unknown>, original: Record<string, unknown>): boolean {
  const snapshot = record(plan.snapshot), reader = record(snapshot.reader), remote = record(snapshot.remote_outcome),
    binding = record(snapshot.binding), parent = record(plan.parent);
  if (!keys(plan, "created_at,expires_at,kind,operation_id,parent,registry_schema_after,registry_schema_before,schema_version,snapshot,state_parent") ||
    !keys(snapshot, "binding,local_identity,reader,remote_outcome") ||
    !keys(reader, "account,context,observation,organization") || !keys(parent, "path,physical") ||
    plan.kind !== kind || plan.registry_schema_after !== 62 || checkoutPath(parent.path) === null ||
    typeof plan.created_at !== "string" || typeof plan.expires_at !== "string" ||
    remote.state !== "applied" || record(remote.plan).plan_id !== record(binding.link).plan_id ||
    record(remote.plan).plan_digest !== record(binding.link).plan_digest ||
    typeof remote.authorization_revision !== "string" ||
    remote.authorization_revision !== record(record(reader.observation).capabilities).authorization_revision ||
    !Array.isArray(record(record(reader.observation).capabilities).capabilities) ||
    !(record(record(reader.observation).capabilities).capabilities as unknown[]).includes("project.link")) return false;
  if (!locationPhysical(parent.physical)) return false;
  // Reuse the immutable original-lineage checks, not the present-root action.
  // Parent identity and absence are proved by native capabilities, never JS path parsing.
  const equivalent: Record<string, unknown> = { ...plan, registry_schema_after: Number(plan.registry_schema_before) >= 61 ? plan.registry_schema_before : 60,
    snapshot: { ...reader, binding, remote_link: remote.link } };
  delete equivalent.kind;
  delete equivalent.parent;
  return bindingRetirementAnchored(equivalent, original);
}

export function missingBindingRetirementReview(response: CmdResult, context: ContextView, original: Record<string, unknown>): BindingRetirementReview | null {
  const plan = record(response.data?.plan), reader = record(record(plan.snapshot).reader), account = record(reader.account);
  if (!response.ok || !hash(response.data?.plan_digest) || !anchored(plan, original) || context.mode !== "corporate" ||
    record(reader.context).context_id !== context.id || account.origin !== context.origin ||
    (record(account.connection).connection_id ?? null) !== context.connection) return null;
  return { plan, digest: response.data.plan_digest };
}

export function missingBindingRetirementReceipt(value: unknown, original: Record<string, unknown>): boolean {
  const receipt = record(value), plan = record(receipt.plan), binding = record(record(plan.snapshot).binding);
  return anchored(plan, original) && hash(receipt.plan_digest) && receipt.operation_id === plan.operation_id &&
    receipt.state === "verified" && receipt.outcome === "missing_checkout_binding_retired" && receipt.checkout_observation === "absent" &&
    receipt.binding_operation_id === record(binding.source).operation_id && receipt.original_request_operation_id === record(binding.request).operation_id &&
    receipt.local_binding_retired === true && receipt.reservation_released === true && receipt.remote_write_submitted === false &&
    receipt.harness_files_changed === false && receipt.tasks_changed === false && receipt.installation_authority === false;
}
