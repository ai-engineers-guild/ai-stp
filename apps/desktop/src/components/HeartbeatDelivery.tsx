import { useText } from "../i18n";
import { useLayoutEffect, useRef, useState } from "react";
import { record, type ContextView } from "../contexts";
import {
  consentReview,
  delivery,
  heartbeatSupported,
  type HeartbeatReview,
} from "../heartbeat";
import {
  cliApplyConfirmed,
  cliPlan,
  cmdHeartbeatConsentApply,
  cmdRunRead,
  type CmdResult,
} from "../transport";
import { Details, ResultMeta, Spinner } from "./Result";
import { scalarText } from "../contracts";

export default function HeartbeatDelivery({
  context,
  help,
  disabled,
}: {
  context: ContextView;
  help: CmdResult | null;
  disabled: boolean;
}) {
  const msg = useText();
  const [result, setResult] = useState<CmdResult | null>(null);
  const [review, setReview] = useState<HeartbeatReview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const active = useRef(true),
    sequence = useRef(0);
  // biome-ignore lint/correctness/useExhaustiveDependencies(context.id): Changing context or locking delivery invalidates the reviewed consent.
  // biome-ignore lint/correctness/useExhaustiveDependencies(disabled): Changing context or locking delivery invalidates the reviewed consent.
  useLayoutEffect(() => {
    active.current = true;
    sequence.current++;
    setReview(null);
    setConfirmed(false);
    setResult(null);
    setBusy(false);
    return () => {
      active.current = false;
      sequence.current++;
    };
  }, [context.id, disabled]);
  const supported =
    help?.ok &&
    [
      ["delivery", "read"],
      ["consent plan", "plan"],
      ["consent apply", "apply"],
      ["disable", "apply"],
      ["flush", "apply"],
    ].every(([path, mode]) => heartbeatSupported(help, path, mode));
  const state = result && delivery(result, context);
  const valid = (n: number) => active.current && n === sequence.current;
  async function run(
    action: "read" | "review" | "apply" | "disable" | "flush",
  ) {
    if (
      !supported ||
      disabled ||
      busy ||
      (action === "apply" && (!review || !confirmed))
    )
      return;
    const n = ++sequence.current,
      exact = review;
    setBusy(true);
    setConfirmed(false);
    if (action !== "apply") setReview(null);
    try {
      let response: CmdResult;
      if (action === "apply" && exact) {
        response = await cmdHeartbeatConsentApply(
          exact.plan,
          exact.digest,
          true,
        );
      } else if (action === "review") {
        const local = await cmdRunRead("corporate heartbeat delivery", {
          context: context.id,
        });
        if (!valid(n)) return;
        const original = delivery(local, context);
        if (!original) {
          setResult(local.ok ? failure() : local);
          return;
        }
        response = await cliPlan("corporate heartbeat consent plan", {
          context: context.id,
        });
        if (!valid(n)) return;
        const prepared = consentReview(
          response,
          context,
          original.context_digest,
        );
        if (response.ok && !prepared) response = failure();
        setReview(prepared);
        // Keep the last validated local status alongside the separate review.
        setResult(response.ok ? local : response);
        return;
      } else if (action === "read") {
        response = await cmdRunRead("corporate heartbeat delivery", {
          context: context.id,
        });
      } else {
        response = await cliApplyConfirmed(
          `corporate heartbeat ${action}`,
          { context: context.id },
          [],
          true,
        );
      }
      if (!valid(n)) return;
      const returned = delivery(response, context);
      if (
        response.ok &&
        (!returned ||
          (action === "apply" &&
            returned.context_digest !== exact?.contextDigest))
      )
        response = failure();
      setResult(response);
      if (response.ok) setReview(null);
    } finally {
      if (valid(n)) setBusy(false);
    }
  }
  const locked = busy || disabled || !supported;
  const observedPolicy = record(review?.plan.policy);
  const interval = observedPolicy.interval_seconds;
  const retry = observedPolicy.retry_base_seconds;
  return (
    <section
      aria-label={msg("heartbeatDelivery.foregroundHeartbeatDelivery")}
      className="space-y-3 border-t border-border pt-4"
    >
      <h3 className="font-medium">
        {msg("heartbeatDelivery.foregroundDeviceLiveness")}
      </h3>
      <p className="text-sm text-muted-foreground">
        {msg("heartbeatDelivery.offUntilYouApproveThisCompanyContextAndPolicy")}
      </p>
      {!supported && (
        <p>
          {msg(
            "heartbeatDelivery.thisEngineDoesNotAdvertiseForegroundHeartbeatDelivery",
          )}
        </p>
      )}
      <button
        type="button"
        className="btn-outline"
        disabled={locked}
        onClick={() => void run("read")}
      >
        {msg("heartbeatDelivery.readLocalDelivery")}
      </button>
      <button
        type="button"
        className="btn-outline"
        disabled={locked || !!review}
        onClick={() => void run("review")}
      >
        {msg("heartbeatDelivery.reviewHeartbeatConsent")}
      </button>
      <button
        type="button"
        className="btn-outline"
        disabled={locked}
        onClick={() => void run("disable")}
      >
        {msg("heartbeatDelivery.disableLocalReporting")}
      </button>
      {busy && (
        <Spinner
          label={msg("heartbeatDelivery.readingTheOriginalHeartbeatContext")}
        />
      )}
      {result && <ResultMeta r={result} />}
      {state && (
        <>
          <p role="status">
            {msg("heartbeatDelivery.localReporting")}{" "}
            {state.enabled
              ? msg("heartbeatDelivery.enabled")
              : msg("heartbeatDelivery.disabled")}
            .{" "}
            {state.pending
              ? msg(
                  "heartbeatDelivery.anOriginalObservationIsAwaitingConfirmation",
                )
              : msg("heartbeatDelivery.noQueuedObservation")}
          </p>
          <p className="text-sm">
            {msg("heartbeatDelivery.lastOutcome")}{" "}
            {scalarText(state.last_outcome ?? msg("common.none"))}
            {msg("heartbeatDelivery.lastConfirmedDelivery")}{" "}
            {scalarText(state.last_success_at ?? msg("common.none"))}.
          </p>
          <button
            type="button"
            className="btn-outline"
            disabled={locked || !state.enabled || !!review}
            onClick={() => void run("flush")}
          >
            {msg("heartbeatDelivery.checkDueHeartbeatDelivery")}
          </button>
        </>
      )}
      {review && (
        <section
          className="space-y-3"
          aria-label={msg("heartbeatDelivery.reviewHeartbeatConsent")}
        >
          <p>
            {msg("heartbeatDelivery.company")} {context.organization}
            {msg("heartbeatDelivery.policyVersion")}{" "}
            {String(review.plan.policy_version)}.
          </p>
          <p className="text-sm">
            {typeof interval === "number" &&
            Number.isFinite(interval) &&
            typeof retry === "number" &&
            Number.isFinite(retry)
              ? msg("heartbeatDelivery.intervalHelp", { interval, retry })
              : msg("heartbeatDelivery.intervalUnavailable")}
          </p>
          <p className="text-sm">
            {msg(
              "heartbeatDelivery.reportsAccountDeviceIdsCliVersionTheFixedCli",
            )}
          </p>
          <p className="font-mono text-xs break-all">{review.digest}</p>
          <Details
            label={msg("heartbeatDelivery.originalHeartbeatConsentPlan")}
            value={review.plan}
          />
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={locked}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            {msg(
              "heartbeatDelivery.iApproveReportingForThisOriginalContextAndPolicy",
            )}
          </label>
          <button
            type="button"
            className="btn-primary"
            disabled={locked || !confirmed}
            onClick={() => void run("apply")}
          >
            {msg("heartbeatDelivery.enableReviewedHeartbeatReporting")}
          </button>
          <button
            type="button"
            className="btn-outline"
            disabled={locked}
            onClick={() => {
              setReview(null);
              setConfirmed(false);
            }}
          >
            {msg("heartbeatDelivery.discardConsentReview")}
          </button>
        </section>
      )}
    </section>
  );
}
function failure(): CmdResult {
  return {
    ok: false,
    data: null,
    error:
      "The heartbeat reply does not match the original context. Read it again.",
    error_code: "HEARTBEAT_VIEW",
    warnings: [],
    continuations: [],
  };
}
