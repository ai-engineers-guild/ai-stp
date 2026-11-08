import { useText } from "../i18n";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { record, records, type ContextView } from "../contexts";
import { checkoutFailure, checkoutPath } from "../checkoutLinks";
import {
  locationHistory,
  locationReceipt,
  locationReview,
  sameLocationValue,
  type LocationAction,
  type LocationEntry,
  type LocationReview,
} from "../checkoutLocation";
import {
  cliPlan,
  cmdCheckoutLocationApply,
  cmdMachineHelp,
  cmdRunRead,
  type CmdResult,
} from "../transport";
import { Details, ResultMeta, Spinner } from "./Result";

interface Props {
  original: Record<string, unknown>;
  context: ContextView | null;
  reader: string | undefined;
  disabled: boolean;
  onBusyChange: (busy: boolean) => void;
}

export default function CheckoutLocation({
  original,
  context,
  reader,
  disabled,
  onBusyChange,
}: Props) {
  const msg = useText();
  const binding = String(original.operation_id);
  const [supported, setSupported] = useState(false);
  const [entries, setEntries] = useState<LocationEntry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [review, setReview] = useState<LocationReview | null>(null);
  const [receipt, setReceipt] = useState<LocationReview | null>(null);
  const [result, setResult] = useState<CmdResult | null>(null);
  const [destination, setDestination] = useState("");
  const [git, setGit] = useState("");
  const [reviewedGit, setReviewedGit] = useState<string | undefined>();
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const active = useRef(false),
    epoch = useRef(0);
  useLayoutEffect(() => {
    active.current = true;
    epoch.current++;
    return () => {
      active.current = false;
      epoch.current++;
      onBusyChange(false);
    };
  }, [context?.id, binding, onBusyChange]);
  function start(): number {
    setBusy(true);
    onBusyChange(true);
    setConfirmed(false);
    return ++epoch.current;
  }
  const current = (sequence: number) =>
    active.current && sequence === epoch.current;
  function finish(sequence: number) {
    if (current(sequence)) {
      setBusy(false);
      onBusyChange(false);
    }
  }
  async function load(next?: string) {
    if (busy || disabled) return;
    const sequence = start();
    try {
      const help = await cmdMachineHelp();
      if (!current(sequence)) return;
      const available = [
        ["corporate project location list", "read"],
        ["corporate project location show", "read"],
        ["corporate project location-anchor plan", "plan"],
        ["corporate project location-relocate plan", "plan"],
        ["corporate project location apply", "apply"],
      ].every(([path, mutability]) =>
        records(help.data?.commands).some(
          (item) =>
            Array.isArray(item.path) &&
            item.path.join(" ") === path &&
            item.mutability === mutability,
        ),
      );
      setSupported(available);
      if (!available) return;
      const values: Record<string, string> = { "binding-operation": binding };
      if (next) values.cursor = next;
      let response = await cmdRunRead(
        "corporate project location list",
        values,
      );
      if (!current(sequence)) return;
      const page = locationHistory(response, binding);
      if (response.ok && !page) response = checkoutFailure();
      setResult(response);
      if (page) {
        setEntries((previous) =>
          next
            ? [
                ...previous,
                ...page.entries.filter(
                  (entry) =>
                    !previous.some(
                      (held) => held.operation_id === entry.operation_id,
                    ),
                ),
              ]
            : page.entries,
        );
        setCursor(page.cursor);
      }
    } finally {
      finish(sequence);
    }
  }
  useEffect(() => {
    void load();
  }, []);

  async function inspect(id: string, digest?: string) {
    if (busy || disabled) return;
    const sequence = start();
    setReceipt(null);
    try {
      let response = await cmdRunRead("corporate project location show", {
        operation: id,
      });
      if (!current(sequence)) return;
      const exact = locationReceipt(response.data, original);
      if (
        response.ok &&
        (!exact ||
          exact.plan.operation_id !== id ||
          (digest !== undefined && exact.digest !== digest))
      )
        response = checkoutFailure();
      setResult(response);
      if (response.ok && exact) {
        setReceipt(exact);
        if (review?.plan.operation_id === id && review.digest === exact.digest)
          setReview(null);
      }
    } finally {
      finish(sequence);
    }
  }
  async function prepare(action: LocationAction) {
    if (
      !context ||
      !reader ||
      !supported ||
      review ||
      original.binding_retirement != null ||
      busy ||
      disabled
    )
      return;
    const sequence = start(),
      trustedGit = git.trim() ? git : undefined;
    const values: Record<string, string> = {
      context: reader,
      "binding-operation": binding,
    };
    if (action === "relocate") values.root = destination;
    if (trustedGit) values["git-executable"] = trustedGit;
    try {
      let response = await cliPlan(
        `corporate project location-${action} plan`,
        values,
      );
      if (!current(sequence)) return;
      const exact = locationReview(
        response,
        action,
        context,
        original,
        destination,
      );
      if (response.ok && !exact) response = checkoutFailure();
      setResult(response);
      if (exact) {
        setReview(exact);
        setReviewedGit(trustedGit);
      }
    } finally {
      finish(sequence);
    }
  }
  async function apply() {
    if (!review || !reader || !confirmed || busy || disabled) return;
    const exact = review,
      sequence = start();
    try {
      let response = await cmdCheckoutLocationApply(
        exact.plan,
        exact.digest,
        true,
        reviewedGit,
      );
      if (!current(sequence)) return;
      const retained = locationReceipt(response.data, original);
      if (
        response.ok &&
        (!retained ||
          retained.digest !== exact.digest ||
          !sameLocationValue(retained.plan, exact.plan))
      )
        response = checkoutFailure();
      setResult(response);
      if (response.ok && retained) {
        setReceipt(retained);
        setReview(null);
      }
    } finally {
      finish(sequence);
    }
  }
  const locked = busy || disabled;
  return (
    <section
      className="space-y-3 border-t border-border pt-4"
      aria-label={msg("checkoutLocation.checkoutLocation")}
    >
      <h3 className="font-medium">
        {msg("checkoutLocation.checkoutLocation")}
      </h3>
      <p className="text-sm">
        {msg("checkoutLocation.originalAdoptionDirectory")}
      </p>
      <p className="break-all font-mono text-xs">
        {checkoutPath(record(original.plan).checkout_root)}
      </p>
      <p className="text-sm text-muted-foreground">
        {msg(
          "checkoutLocation.locationReceiptsRecordEarlierReviewsReadAFreshNative",
        )}
      </p>
      <button
        className="btn-outline"
        disabled={locked}
        onClick={() => void load()}
      >
        {msg("checkoutLocation.readLocationHistory")}
      </button>
      {busy && (
        <Spinner
          label={msg("checkoutLocation.readingTheOriginalCheckoutLocation")}
        />
      )}
      {!busy && !supported && (
        <p className="text-sm text-muted-foreground">
          {msg(
            "checkoutLocation.thisEngineDoesNotExposeReviewedCheckoutLocations",
          )}
        </p>
      )}
      {result && <ResultMeta r={result} />}
      {supported && (
        <>
          {entries.length === 0 && !busy && (
            <p>{msg("checkoutLocation.noRecordedLocationReceipts")}</p>
          )}
          {entries.length > 0 && (
            <ul
              className="space-y-2"
              aria-label={msg("checkoutLocation.recordedCheckoutLocations")}
            >
              {entries.map((entry) => (
                <li className="space-y-1" key={entry.operation_id}>
                  <p className="text-sm">
                    {entry.action === "anchor"
                      ? msg("checkoutLocation.reviewedAnchor")
                      : msg("checkoutLocation.reviewedRelocation")}{" "}
                    · {entry.completed_at}
                  </p>
                  <p className="break-all font-mono text-xs">
                    {checkoutPath(entry.root)}
                  </p>
                  <button
                    className="btn-outline"
                    disabled={locked}
                    onClick={() =>
                      void inspect(entry.operation_id, entry.plan_digest)
                    }
                  >
                    {msg("checkoutLocation.inspectLocation")}{" "}
                    {entry.operation_id}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {cursor && (
            <button
              className="btn-outline"
              disabled={locked}
              onClick={() => void load(cursor)}
            >
              {msg("checkoutLocation.readMoreLocationHistory")}
            </button>
          )}
          {receipt && (
            <div
              className="space-y-2"
              aria-label={msg("checkoutLocation.recordedLocationReceipt")}
            >
              <p role="status">
                {receipt.action === "anchor"
                  ? msg("checkoutLocation.checkoutAnchorReceiptSaved")
                  : msg("checkoutLocation.checkoutRelocationReceiptSaved")}
              </p>
              <p className="text-sm">
                {msg("checkoutLocation.recordedDirectory")}
              </p>
              <p className="break-all font-mono text-xs">
                {checkoutPath(receipt.plan.destination)}
              </p>
              <p className="break-all font-mono text-xs">
                {String(receipt.plan.operation_id)} · {receipt.digest}
              </p>
              <Details
                label={msg("checkoutLocation.originalLocationReceiptPlan")}
                value={receipt.plan}
              />
            </div>
          )}
          {original.binding_retirement == null && (
            <>
              {!reader && (
                <p>
                  {msg(
                    "checkoutLocation.selectACurrentContextForTheSameAccountAnd",
                  )}
                </p>
              )}
              <p className="text-sm text-muted-foreground">
                {msg(
                  "checkoutLocation.beforeMovingACheckoutReviewAndSaveAnAnchor",
                )}
              </p>
              <label className="field-label">
                {msg(
                  "checkoutLocation.trustedGitExecutableForLocationReviewOptional",
                )}
                <input
                  className="input"
                  value={git}
                  disabled={locked || !!review}
                  onChange={(event) => setGit(event.target.value)}
                />
              </label>
              <button
                className="btn-outline"
                disabled={locked || !reader || !!review}
                onClick={() => void prepare("anchor")}
              >
                {msg("checkoutLocation.reviewCheckoutAnchor")}
              </button>
              <label className="field-label">
                {msg("checkoutLocation.existingMovedCheckoutDirectory")}
                <input
                  className="input"
                  value={destination}
                  disabled={locked || !!review}
                  onChange={(event) => setDestination(event.target.value)}
                />
              </label>
              <button
                className="btn-outline"
                disabled={locked || !reader || !!review || !destination.trim()}
                onClick={() => void prepare("relocate")}
              >
                {msg("checkoutLocation.reviewMovedCheckout")}
              </button>
            </>
          )}
          {review && (
            <section
              className="space-y-3"
              aria-label={msg("checkoutLocation.reviewCheckoutLocation")}
            >
              <h4 className="font-medium">
                {review.action === "anchor"
                  ? msg("checkoutLocation.reviewPresentCheckoutAnchor")
                  : msg("checkoutLocation.reviewManuallyMovedCheckout")}
              </h4>
              <p className="text-sm">
                {msg("checkoutLocation.previouslyRegisteredDirectory")}
              </p>
              <p className="break-all font-mono text-xs">
                {checkoutPath(record(review.plan.binding).checkout_root)}
              </p>
              <p className="text-sm">
                {msg("checkoutLocation.reviewedDestination")}
              </p>
              <p className="break-all font-mono text-xs">
                {checkoutPath(review.plan.destination)}
              </p>
              <p className="break-all font-mono text-xs">
                {String(review.plan.operation_id)} · {review.digest}
              </p>
              <Details
                label={msg("checkoutLocation.exactCheckoutLocationPlan")}
                value={review.plan}
              />
              <label className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={locked || !reader}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                {msg(
                  "checkoutLocation.iReviewedThisExactCheckoutLocationAndAuthorizeSaving",
                )}
              </label>
              <button
                className="btn-primary"
                disabled={locked || !reader || !confirmed}
                onClick={() => void apply()}
              >
                {msg("checkoutLocation.applyReviewedCheckoutLocation")}
              </button>
              <button
                className="btn-outline"
                disabled={locked}
                onClick={() =>
                  void inspect(String(review.plan.operation_id), review.digest)
                }
              >
                {msg("checkoutLocation.readThisLocationOutcome")}
              </button>
              <button
                className="btn-outline"
                disabled={locked}
                onClick={() => {
                  setReview(null);
                  setConfirmed(false);
                }}
              >
                {msg("checkoutLocation.closeLocationReview")}
              </button>
              <p className="text-xs text-muted-foreground">
                {msg(
                  "checkoutLocation.anUnconfirmedReplyKeepsThisExactPlanReadIts",
                )}
              </p>
            </section>
          )}
        </>
      )}
    </section>
  );
}
