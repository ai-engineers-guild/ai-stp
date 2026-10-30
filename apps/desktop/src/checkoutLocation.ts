import { record, type ContextView } from "./contexts";
import { checkoutPath, retainedCheckout } from "./checkoutLinks";
import type { CmdResult } from "./transport";

export type LocationAction = "anchor" | "relocate";
export interface LocationReview {
  plan: Record<string, unknown>;
  digest: string;
  action: LocationAction;
}
export interface LocationEntry {
  operation_id: string;
  plan_digest: string;
  action: LocationAction;
  root: unknown;
  state: "verified";
  created_at: string;
  completed_at: string;
}
const operation = (value: unknown): value is string => typeof value === "string" &&
  /^operation_[0-7][0-9A-HJKMNP-TV-Z]{25}$/.test(value);
const hash = (value: unknown): value is string => typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);
const timestamp = (value: unknown): value is string => typeof value === "string" &&
  /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z$/.test(value) && Number.isFinite(Date.parse(value));

/** Compare public JSON without depending on object insertion order. */
export function sameLocationValue(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) &&
    left.length === right.length && left.every((value, index) => sameLocationValue(value, right[index]));
  if (!left || !right || typeof left !== "object" || typeof right !== "object") return false;
  const a = record(left), b = record(right), keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every((key) => Object.hasOwn(b, key) && sameLocationValue(a[key], b[key]));
}
function decimal(value: unknown, bits: 64 | 128): boolean {
  return typeof value === "string" && value.length <= 39 && /^(0|[1-9][0-9]*)$/.test(value) &&
    BigInt(value) < (1n << BigInt(bits));
}
export function locationPhysical(value: unknown): boolean {
  const physical = record(value);
  if (physical.kind === "unix") return Object.keys(physical).sort().join(",") === "device,inode,kind" &&
    decimal(physical.device, 64) && decimal(physical.inode, 64);
  return physical.kind === "windows" && Object.keys(physical).sort().join(",") === "file_id,kind,volume" &&
    decimal(physical.volume, 64) && decimal(physical.file_id, 128);
}
function locator(value: unknown, plan: Record<string, unknown>): boolean {
  const held = record(value), binding = record(plan.binding);
  return Object.keys(held).sort().join(",") === "operation_id,physical,plan_digest" &&
    operation(held.operation_id) && hash(held.plan_digest) && locationPhysical(held.physical) &&
    ![plan.operation_id, record(binding.source).operation_id, record(binding.request).operation_id].includes(held.operation_id);
}

function anchored(plan: Record<string, unknown>, original: Record<string, unknown>): boolean {
  const source = retainedCheckout(original);
  if (!source || source.action !== "adopt" || original.state !== "completed") return false;
  const snapshot = record(record(source.plan.change).snapshot),
    binding = record(plan.binding), local = record(snapshot.local_project),
    root = record(local.root), reader = record(plan.reader), context = record(reader.context),
    account = record(reader.account), originalAccount = record(snapshot.account),
    organization = record(reader.organization), remote = record(plan.remote),
    link = record(record(original.effect).link), cached = record(binding.link), observed = record(remote.link),
    physical = record(plan.physical), relocation = record(plan.relocation);
  const coordinates = ["link_id", "organization_id", "local_project_id", "remote_project_id", "provider_project_id", "plan_id", "plan_digest"];
  const current = checkoutPath(binding.checkout_root), destination = checkoutPath(plan.destination);
  if (plan.schema_version !== 1 || !operation(plan.operation_id) || !operation(source.plan.operation_id) ||
    !operation(record(binding.request).operation_id) ||
    [source.plan.operation_id, record(binding.request).operation_id].includes(plan.operation_id) ||
    ![57, 58, 59, 60, 61, 62].includes(Number(plan.registry_schema_before)) ||
    typeof plan.registry_schema_before !== "number" || plan.registry_schema_after !== (plan.registry_schema_before === 62 ? 62 : 61) ||
    !timestamp(plan.created_at) || !timestamp(plan.expires_at) || plan.created_at >= plan.expires_at ||
    !sameLocationValue(plan.original, source.plan) ||
    checkoutPath(plan.state_parent) === null || checkoutPath(plan.state_parent) !== checkoutPath(source.plan.state_parent) ||
    !sameLocationValue(plan.state_parent, context.root) || !sameLocationValue(plan.local_identity, context.local_identity) ||
    !plan.local_identity || !sameLocationValue(binding.account, originalAccount) ||
    !sameLocationValue(binding.context, snapshot.context) ||
    record(binding.source).operation_id !== source.plan.operation_id || record(binding.source).plan_digest !== source.digest ||
    record(binding.request).operation_id !== record(source.plan.change).request_operation_id || !hash(record(binding.request).plan_digest) ||
    record(binding.reservation).binding_operation_id !== source.plan.operation_id ||
    record(binding.reservation).request_operation_id !== record(binding.request).operation_id ||
    record(binding.reservation).local_project_id !== local.local_project_id ||
    record(binding.local_project).stable_id !== local.local_project_id ||
    !Array.isArray(root.identity) || root.identity.length !== 2 || !sameLocationValue(binding.physical_root, root.identity) ||
    current === null || destination === null || checkoutPath(plan.checkout_spelling) === null ||
    !locationPhysical(plan.physical) || !locationPhysical(plan.git_physical) || physical.kind !== record(plan.git_physical).kind ||
    (physical.kind === "unix" && !sameLocationValue([physical.device, physical.inode], binding.physical_root)) ||
    account.origin !== originalAccount.origin || account.account_id !== originalAccount.account_id ||
    organization.organization_id !== record(snapshot.organization).organization_id ||
    record(record(context.authority).account).origin !== account.origin ||
    record(record(context.authority).account).account_id !== account.account_id ||
    record(record(context.authority).organization).organization_id !== organization.organization_id ||
    record(context.authority).kind !== "remote" ||
    remote.state !== "applied" || !["linked", "conflict"].includes(String(observed.state)) ||
    !coordinates.every((field) => field in link && cached[field] === link[field] && observed[field] === link[field]) ||
    (binding.location != null && (!locator(binding.location, plan) || ![61, 62].includes(Number(plan.registry_schema_before))))) return false;
  if (binding.location == null && current !== checkoutPath(source.plan.checkout_root)) return false;
  if (plan.action === "anchor") return destination === current && plan.relocation === null;
  return plan.action === "relocate" && binding.location != null &&
    sameLocationValue(record(binding.location).physical, plan.physical) && destination !== current &&
    checkoutPath(relocation.root) === destination && checkoutPath(relocation.previous_root) === current &&
    sameLocationValue(relocation.previous, binding.local_project) &&
    sameLocationValue(relocation.root_identity, binding.physical_root);
}

export function locationReview(response: CmdResult, action: LocationAction, context: ContextView,
  original: Record<string, unknown>, destination?: string): LocationReview | null {
  const plan = record(response.data?.plan), reader = record(plan.reader), current = record(reader.context), account = record(reader.account);
  if (!response.ok || !hash(response.data?.plan_digest) || !anchored(plan, original) || plan.action !== action ||
    context.mode !== "corporate" || current.context_id !== context.id || account.origin !== context.origin ||
    (record(account.connection).connection_id ?? null) !== context.connection ||
    (action === "relocate" && checkoutPath(plan.destination) !== destination)) return null;
  return { plan, digest: response.data.plan_digest, action };
}

/** Completed evidence stays original even after another move or retirement. */
export function locationReceipt(value: unknown, original: Record<string, unknown>): LocationReview | null {
  const receipt = record(value), plan = record(receipt.plan);
  if (!anchored(plan, original) || !hash(receipt.plan_digest) || receipt.operation_id !== plan.operation_id ||
    receipt.binding_operation_id !== record(record(plan.binding).source).operation_id || receipt.state !== "verified" ||
    receipt.outcome !== (plan.action === "anchor" ? "location_anchored" : "checkout_relocated") ||
    !["remote_write_submitted", "harness_files_changed", "tasks_changed", "installation_authority"].every((field) => receipt[field] === false)) return null;
  return { plan, digest: receipt.plan_digest, action: plan.action as LocationAction };
}

export function locationHistory(response: CmdResult, binding: string): { entries: LocationEntry[]; cursor: string | null } | null {
  const data = response.data;
  if (!response.ok || !data || data.schema_version !== 1 || data.binding_operation_id !== binding || data.installation_authority !== false ||
    !Array.isArray(data.locations) || data.locations.length > 100 || (data.next_cursor !== null && !operation(data.next_cursor))) return null;
  const seen = new Set<string>();
  for (const item of data.locations) {
    const entry = record(item);
    if (!operation(entry.operation_id) || seen.has(entry.operation_id) || !hash(entry.plan_digest) ||
      !["anchor", "relocate"].includes(String(entry.action)) || entry.state !== "verified" || checkoutPath(entry.root) === null ||
      !timestamp(entry.created_at) || !timestamp(entry.completed_at) || entry.completed_at < entry.created_at) return null;
    seen.add(entry.operation_id);
  }
  if (data.next_cursor !== null && (data.locations.length !== 100 || data.next_cursor !== record(data.locations.at(-1)).operation_id)) return null;
  return { entries: data.locations as LocationEntry[], cursor: data.next_cursor as string | null };
}
