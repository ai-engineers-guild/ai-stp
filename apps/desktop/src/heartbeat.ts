import { record, records, type ContextView } from "./contexts";
import { cliApplyConfirmed, cmdMachineHelp, cmdRunRead, type CmdResult } from "./transport";

const prefix = "corporate heartbeat ";
export const hash = (value: unknown): value is string => typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);
export function heartbeatSupported(help: CmdResult, path: string, mutability: string): boolean {
  return help.ok && records(help.data?.commands).some((command) =>
    Array.isArray(command.path) && command.path.join(" ") === prefix + path && command.mutability === mutability);
}
export function delivery(response: CmdResult, context: ContextView): Record<string, unknown> | null {
  const data = response.data;
  return response.ok && data?.schema_version === 1 && data.context_id === context.id && hash(data.context_digest) &&
    typeof data.enabled === "boolean" && typeof data.pending === "boolean" && Number.isInteger(data.attempts) &&
    Number(data.attempts) >= 0 && Number(data.attempts) <= 8 && data.scheduler_registered === false &&
    data.coverage === "cli_foreground_liveness_only" ? data : null;
}
export interface HeartbeatReview { plan: Record<string, unknown>; digest: string; contextDigest: string }
export function consentReview(response: CmdResult, context: ContextView, contextDigest: unknown): HeartbeatReview | null {
  const data = response.data, plan = record(data?.plan), original = record(plan.context), authority = record(original.authority);
  const account = record(plan.account), bound = record(authority.account), organization = record(authority.organization);
  const disclosure = record(data?.disclosure);
  const policy = record(plan.policy);
  if (!response.ok || !hash(data?.plan_digest) || !hash(contextDigest) || data.context_digest !== contextDigest ||
    plan.schema_version !== 1 || plan.action !== "corporate.heartbeat.consent" ||
    typeof plan.plan_id !== "string" || !/^plan_[0-7][0-9A-HJKMNP-TV-Z]{25}$/.test(plan.plan_id) ||
    original.context_id !== context.id || context.mode !== "corporate" || authority.kind !== "remote" || organization.kind !== "corporate" ||
    account.origin !== context.origin || bound.origin !== context.origin ||
    (record(account.connection).connection_id ?? null) !== context.connection ||
    (record(bound.connection).connection_id ?? null) !== context.connection ||
    account.account_id !== bound.account_id || account.device_id !== bound.device_id || account.public_key !== bound.public_key ||
    !Number.isSafeInteger(plan.policy_version) || Number(plan.policy_version) < 0 ||
    policy.policy_version !== plan.policy_version || policy.enabled !== true ||
    !Number.isSafeInteger(policy.interval_seconds) || Number(policy.interval_seconds) < 60 ||
    typeof plan.created_at !== "string" || typeof plan.expires_at !== "string" ||
    !Number.isFinite(Date.parse(plan.created_at)) || Date.parse(plan.expires_at) - Date.parse(plan.created_at) !== 600000 ||
    disclosure.coverage !== "cli_foreground_liveness_only" || disclosure.harness_runtime_coverage !== "unknown" ||
    disclosure.managed_inventory !== "none" || disclosure.startup_service_installed !== false) return null;
  return { plan: structuredClone(plan), digest: data.plan_digest, contextDigest };
}

/** A single bounded foreground pass. Native consent, original identity, policy,
 * cadence, retries and payload retention remain authoritative in the CLI. */
export async function foregroundHeartbeat(context: ContextView | null, current: () => boolean): Promise<void> {
  const help = await cmdMachineHelp();
  if (!current() || !help.ok) return;
  if (heartbeatSupported(help, "maintain", "apply")) {
    await cliApplyConfirmed(prefix + "maintain", {}, [], true);
  }
  if (!current() || context?.mode !== "corporate" ||
    !heartbeatSupported(help, "delivery", "read") || !heartbeatSupported(help, "flush", "apply")) return;
  const response = await cmdRunRead(prefix + "delivery", { context: context.id });
  if (!current() || !delivery(response, context)?.enabled) return;
  await cliApplyConfirmed(prefix + "flush", { context: context.id }, [], true);
}
