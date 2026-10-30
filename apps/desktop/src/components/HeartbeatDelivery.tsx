import { useLayoutEffect, useRef, useState } from "react";
import { record, type ContextView } from "../contexts";
import { consentReview, delivery, heartbeatSupported, type HeartbeatReview } from "../heartbeat";
import { cliApplyConfirmed, cliPlan, cmdHeartbeatConsentApply, cmdRunRead, type CmdResult } from "../transport";
import { Details, ResultMeta, Spinner } from "./Result";

export default function HeartbeatDelivery({ context, help, disabled }: { context: ContextView; help: CmdResult | null; disabled: boolean }) {
  const [result, setResult] = useState<CmdResult | null>(null);
  const [review, setReview] = useState<HeartbeatReview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const active = useRef(true), sequence = useRef(0);
  useLayoutEffect(() => {
    active.current = true; sequence.current++; setReview(null); setConfirmed(false); setResult(null); setBusy(false);
    return () => { active.current = false; sequence.current++; };
  }, [context.id, disabled]);
  const supported = help?.ok && [["delivery", "read"], ["consent plan", "plan"], ["consent apply", "apply"], ["disable", "apply"], ["flush", "apply"]]
    .every(([path, mode]) => heartbeatSupported(help, path, mode));
  const state = result && delivery(result, context);
  const valid = (n: number) => active.current && n === sequence.current;
  async function run(action: "read" | "review" | "apply" | "disable" | "flush") {
    if (!supported || disabled || busy || (action === "apply" && (!review || !confirmed))) return;
    const n = ++sequence.current, exact = review;
    setBusy(true); setConfirmed(false);
    if (action !== "apply") setReview(null);
    try {
      let response: CmdResult;
      if (action === "apply" && exact) {
        response = await cmdHeartbeatConsentApply(exact.plan, exact.digest, true);
      } else if (action === "review") {
        const local = await cmdRunRead("corporate heartbeat delivery", { context: context.id });
        if (!valid(n)) return;
        const original = delivery(local, context);
        if (!original) { setResult(local.ok ? failure() : local); return; }
        response = await cliPlan("corporate heartbeat consent plan", { context: context.id });
        if (!valid(n)) return;
        const prepared = consentReview(response, context, original.context_digest);
        if (response.ok && !prepared) response = failure();
        setReview(prepared);
        // Keep the last validated local status alongside the separate review.
        setResult(response.ok ? local : response);
        return;
      } else if (action === "read") {
        response = await cmdRunRead("corporate heartbeat delivery", { context: context.id });
      } else {
        response = await cliApplyConfirmed(`corporate heartbeat ${action}`, { context: context.id }, [], true);
      }
      if (!valid(n)) return;
      const returned = delivery(response, context);
      if (response.ok && (!returned || (action === "apply" && returned.context_digest !== exact?.contextDigest))) response = failure();
      setResult(response);
      if (response.ok) setReview(null);
    } finally { if (valid(n)) setBusy(false); }
  }
  const locked = busy || disabled || !supported;
  return <section aria-label="Foreground heartbeat delivery" className="space-y-3 border-t border-border pt-4">
    <h3 className="font-medium">Foreground device liveness</h3>
    <p className="text-sm text-muted-foreground">Off until you approve this company context and policy. While this app is focused, it can report this CLI's liveness. Harness activity and managed installation coverage remain unknown. No startup service is installed.</p>
    {!supported && <p>This engine does not advertise foreground heartbeat delivery.</p>}
    <button className="btn-outline" disabled={locked} onClick={() => void run("read")}>Read local delivery</button>
    <button className="btn-outline" disabled={locked || !!review} onClick={() => void run("review")}>Review heartbeat consent</button>
    <button className="btn-outline" disabled={locked} onClick={() => void run("disable")}>Disable local reporting</button>
    {busy && <Spinner label="Reading the original heartbeat context" />}
    {result && <ResultMeta r={result} />}
    {state && <>
      <p role="status">Local reporting: {state.enabled ? "enabled" : "disabled"}. {state.pending ? "An original observation is awaiting confirmation." : "No queued observation."}</p>
      <p className="text-sm">Last outcome: {String(state.last_outcome ?? "none")}. Last confirmed delivery: {String(state.last_success_at ?? "none")}.</p>
      <button className="btn-outline" disabled={locked || !state.enabled || !!review} onClick={() => void run("flush")}>Check due heartbeat delivery</button>
    </>}
    {review && <div className="space-y-3" aria-label="Review heartbeat consent">
      <p>Company: {context.organization}. Policy version: {String(review.plan.policy_version)}.</p>
      <p className="text-sm">Observation interval: {String(record(review.plan.policy).interval_seconds)} seconds. Retries start after {String(record(review.plan.policy).retry_base_seconds)} seconds and expire within four minutes.</p>
      <p className="text-sm">Reports account/device IDs, CLI version, the fixed CLI liveness capability, active state, observation time and policy version, signed with the original enrolled device. No last-sync activity is claimed. This does not register harness usage or send installation inventory.</p>
      <p className="break-all font-mono text-xs">{review.digest}</p>
      <Details label="Original heartbeat consent plan" value={review.plan} />
      <label className="flex items-center gap-2"><input type="checkbox" checked={confirmed} disabled={locked} onChange={(event) => setConfirmed(event.target.checked)} />I approve reporting for this original context and policy</label>
      <button className="btn-primary" disabled={locked || !confirmed} onClick={() => void run("apply")}>Enable reviewed heartbeat reporting</button>
      <button className="btn-outline" disabled={locked} onClick={() => { setReview(null); setConfirmed(false); }}>Discard consent review</button>
    </div>}
  </section>;
}
function failure(): CmdResult {
  return { ok: false, data: null, error: "The heartbeat reply does not match the original context. Read it again.", error_code: "HEARTBEAT_VIEW", warnings: [], continuations: [] };
}
