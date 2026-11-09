import { useText } from "../i18n";
import { useCallback, useEffect, useRef, useState } from "react";
import { record, type ContextView } from "../contexts";
import {
  cliApplyConfirmed,
  cliPlan,
  cmdNativeInventoryEnable,
  cmdRunRead,
  type CmdResult,
} from "../transport";
import { Details, ResultMeta } from "./Result";

interface Disclosure {
  plan: Record<string, unknown>;
  digest: string;
  context: string;
  label: string;
}
export default function NativeInventory({ context }: { context: ContextView }) {
  const msg = useText();
  const [status, setStatus] = useState<CmdResult | null>(null);
  const [result, setResult] = useState<CmdResult | null>(null);
  const [review, setReview] = useState<Disclosure | null>(null);
  const [approved, setApproved] = useState(false),
    [busy, setBusy] = useState(false);
  const current = useRef(context.id),
    alive = useRef(true);
  current.current = context.id;
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const refresh = useCallback(async (id: string) => {
    const response = await cmdRunRead("corporate inventory status", {
      context: id,
    });
    if (alive.current && current.current === id) setStatus(response);
  }, []);
  useEffect(() => {
    setStatus(null);
    void refresh(context.id);
  }, [context.id, refresh]);
  async function disclose() {
    const id = context.id;
    setBusy(true);
    setApproved(false);
    try {
      const response = await cliPlan("corporate inventory consent plan", {
        context: id,
      });
      if (!alive.current) return;
      setResult(response);
      const plan = record(response.data?.plan),
        original = record(plan.context);
      const digest = response.data?.plan_digest;
      if (
        response.ok &&
        plan.format === "ai-stp-native-inventory-consent/1" &&
        original.context_id === id &&
        typeof original.label === "string" &&
        typeof digest === "string" &&
        /^sha256:[0-9a-f]{64}$/.test(digest)
      ) {
        setReview({ plan, digest, context: id, label: original.label });
      } else setReview(null);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function enable() {
    const held = review;
    if (!held || !approved || busy) return;
    setBusy(true);
    try {
      const response = await cmdNativeInventoryEnable(
        held.plan,
        held.digest,
        true,
      );
      if (!alive.current) return;
      setResult(response);
      setApproved(false);
      if (response.ok) setReview(null);
      await refresh(held.context);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function run(action: "scan" | "flush" | "disable") {
    if (busy) return;
    const id = context.id;
    setBusy(true);
    try {
      const response = await cliApplyConfirmed(
        "corporate inventory " + action,
        { context: id },
        [],
        true,
      );
      if (!alive.current) return;
      setResult(response);
      await refresh(id);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  const enabled = status?.ok && status.data?.enabled === true;
  return (
    <section
      className="card p-5"
      aria-label={msg("nativeInventory.companyInventory")}
    >
      <h2 className="text-lg font-semibold">
        {msg("nativeInventory.companyInventory")}
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        {msg("nativeInventory.reportsComponentsOwnedByAiStpInThisCompany")}
      </p>
      <p className="mt-3 text-sm">
        {msg("nativeInventory.localConsent")}{" "}
        {status?.ok
          ? enabled
            ? msg("nativeInventory.enabled")
            : msg("nativeInventory.disabled")
          : msg("nativeInventory.unavailable")}{" "}
        · {context.label}
      </p>
      {Boolean(status?.data?.pending_digest) && (
        <p className="mt-2 text-sm">
          {msg(
            "nativeInventory.anExactReportIsWaitingForDeliveryRetryDelivery",
          )}
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          className="btn-secondary"
          disabled={busy}
          onClick={() => void refresh(context.id)}
        >
          {msg("nativeInventory.readConsent")}
        </button>
        {!enabled && (
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={() => void disclose()}
          >
            {msg("nativeInventory.reviewInventoryConsent")}
          </button>
        )}
        {enabled && (
          <>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => void run("scan")}
            >
              {msg("nativeInventory.collectOwnedInventory")}
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy || !status?.data?.pending_digest}
              onClick={() => void run("flush")}
            >
              {msg("nativeInventory.deliverPendingReport")}
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => void run("disable")}
            >
              {msg("nativeInventory.disableLocally")}
            </button>
          </>
        )}
      </div>
      {review && (
        <div className="mt-4 rounded-lg border border-border p-4">
          <p>{msg("nativeInventory.consentFor", { context: review.label })}</p>
          {review.context !== context.id && (
            <p className="mt-2 text-sm">
              {msg(
                "nativeInventory.theViewChangedThisReviewRetainsItsOriginalCompany",
              )}
            </p>
          )}
          <Details
            label={msg("nativeInventory.currentCompanyPolicy")}
            value={review.plan.policy}
          />
          <label className="mt-3 flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={approved}
              disabled={busy}
              onChange={(event) => setApproved(event.target.checked)}
            />
            {msg(
              "nativeInventory.iApproveTheDisclosedInventoryReportingForThisContext",
            )}
          </label>
          <button
            type="button"
            className="btn-primary mt-3"
            disabled={busy || !approved}
            onClick={() => void enable()}
          >
            {msg("nativeInventory.enableReviewedConsent")}
          </button>
        </div>
      )}
      {status && !status.ok && <ResultMeta r={status} />}
      {result && <ResultMeta r={result} />}
    </section>
  );
}
