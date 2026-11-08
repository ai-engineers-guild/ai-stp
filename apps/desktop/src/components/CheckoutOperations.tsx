import { useText } from "../i18n";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { record, records, useContexts } from "../contexts";
import {
  checkoutFailure,
  checkoutPath,
  checkoutReader,
  checkoutReceipt,
  checkoutReview,
  retainedCheckout,
  type CheckoutReview,
} from "../checkoutLinks";
import {
  bindingRetirementReceipt,
  bindingRetirementReview,
  type BindingRetirementReview,
} from "../bindingRetirement";
import {
  missingBindingRetirementReceipt,
  missingBindingRetirementReview,
} from "../missingBindingRetirement";
import {
  cliPlan,
  cmdMissingBindingRetirementApply,
  cmdBindingRetirementApply,
  cmdCheckoutApply,
  cmdMachineHelp,
  cmdRunRead,
  type CmdResult,
} from "../transport";
import { Details, ResultMeta, Spinner } from "./Result";
import CheckoutLocation from "./CheckoutLocation";
import { scalarText } from "../contracts";

export default function CheckoutOperations() {
  const msg = useText();
  const context = useContexts((state) => state.selected);
  const contexts = useContexts((state) => state.result);
  const switching = useContexts((state) => state.loading || state.switching);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [result, setResult] = useState<CmdResult | null>(null);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(
    null,
  );
  const [review, setReview] = useState<CheckoutReview | null>(null);
  const [nextReview, setNextReview] = useState<CheckoutReview | null>(null);
  const [retirement, setRetirement] = useState<BindingRetirementReview | null>(
    null,
  );
  const [missingRetirement, setMissingRetirement] = useState(false);
  const [missingSupported, setMissingSupported] = useState(false);
  const [root, setRoot] = useState("");
  const [git, setGit] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [locationBusy, setLocationBusy] = useState(false);
  const [supported, setSupported] = useState(false);
  const [retirementSupported, setRetirementSupported] = useState(false);
  const active = useRef(false),
    epoch = useRef(0);
  // biome-ignore lint/correctness/useExhaustiveDependencies(context?.id): A context change clears the review and invalidates pending native responses.
  useLayoutEffect(() => {
    active.current = true;
    epoch.current++;
    setReview(null);
    setNextReview(null);
    setRetirement(null);
    setSelected(null);
    setConfirmed(false);
    setResult(null);
    setBusy(false);
    setLocationBusy(false);
    return () => {
      active.current = false;
      epoch.current++;
    };
  }, [context?.id]);

  async function load(next?: string) {
    if (busy || locationBusy || switching) return;
    const sequence = ++epoch.current;
    setBusy(true);
    setReview(null);
    setNextReview(null);
    setRetirement(null);
    setConfirmed(false);
    try {
      const help = await cmdMachineHelp();
      if (!active.current || sequence !== epoch.current) return;
      const available = [
        "corporate project link list",
        "corporate project link show",
      ].every((path) =>
        records(help?.data?.commands).some(
          (item) =>
            Array.isArray(item.path) &&
            item.path.join(" ") === path &&
            item.mutability === "read",
        ),
      );
      setSupported(available);
      setRetirementSupported(
        [
          "corporate project binding-retire plan",
          "corporate project binding-retire apply",
        ].every((path, index) =>
          records(help?.data?.commands).some(
            (item) =>
              Array.isArray(item.path) &&
              item.path.join(" ") === path &&
              item.mutability === (index === 0 ? "plan" : "apply"),
          ),
        ),
      );
      setMissingSupported(
        [
          "corporate project binding-retire-missing plan",
          "corporate project binding-retire-missing apply",
          "corporate project binding-retire-missing show",
        ].every((path, index) =>
          records(help?.data?.commands).some(
            (item) =>
              Array.isArray(item.path) &&
              item.path.join(" ") === path &&
              item.mutability === ["plan", "apply", "read"][index],
          ),
        ),
      );
      if (!available) {
        setRows([]);
        return;
      }
      const values: Record<string, string> = { limit: "50" };
      if (next) values.cursor = next;
      let response = await cmdRunRead("corporate project link list", values);
      if (!active.current || sequence !== epoch.current) return;
      const items = records(response.data?.items);
      if (
        response.ok &&
        (!Array.isArray(response.data?.items) ||
          items.length > 50 ||
          items.some((item) => !retainedCheckout(item)))
      )
        response = checkoutFailure();
      setResult(response);
      if (response.ok) {
        setRows((previous) =>
          next
            ? [
                ...previous,
                ...items.filter(
                  (item) =>
                    !previous.some(
                      (held) => held.operation_id === item.operation_id,
                    ),
                ),
              ]
            : items,
        );
        setCursor(
          typeof response.data?.next_cursor === "string"
            ? response.data.next_cursor
            : null,
        );
      }
    } finally {
      if (active.current && sequence === epoch.current) setBusy(false);
    }
  }
  // biome-ignore lint/correctness/useExhaustiveDependencies(load): Read this mounted receipt once; refresh and pagination explicitly own subsequent reads.
  useEffect(() => {
    void load();
  }, []);

  async function inspect(id: string) {
    if (busy || locationBusy || switching) return;
    const sequence = ++epoch.current;
    setBusy(true);
    setReview(null);
    setNextReview(null);
    setRetirement(null);
    setConfirmed(false);
    try {
      let response = await cmdRunRead("corporate project link show", {
        operation: id,
      });
      if (!active.current || sequence !== epoch.current) return;
      const exact = retainedCheckout(response.data);
      if (response.ok && (!exact || exact.plan.operation_id !== id))
        response = checkoutFailure();
      if (
        response.ok &&
        exact?.action === "adopt" &&
        response.data?.binding_retirement != null &&
        !bindingRetirementReceipt(
          response.data.binding_retirement,
          record(response.data),
        ) &&
        !missingBindingRetirementReceipt(
          response.data.binding_retirement,
          record(response.data),
        )
      )
        response = checkoutFailure();
      setResult(response);
      if (response.ok && exact) {
        setSelected(record(response.data));
        setReview(exact);
        setRoot(checkoutPath(exact.plan.checkout_root) ?? "");
        setGit("");
      }
    } finally {
      if (active.current && sequence === epoch.current) setBusy(false);
    }
  }

  const reader = review ? checkoutReader(context, contexts, review) : undefined;
  async function prepareRetirement(missing = false) {
    if (
      !selected ||
      !review ||
      review.action !== "adopt" ||
      selected.state !== "completed" ||
      !reader ||
      !context ||
      !(missing ? missingSupported : retirementSupported) ||
      retirement ||
      selected.binding_retirement !== null ||
      busy ||
      locationBusy ||
      switching
    )
      return;
    const original = selected,
      sequence = ++epoch.current;
    setBusy(true);
    setConfirmed(false);
    try {
      let response = await cliPlan(
        missing
          ? "corporate project binding-retire-missing plan"
          : "corporate project binding-retire plan",
        {
          context: reader,
          "binding-operation": String(review.plan.operation_id),
        },
      );
      if (!active.current || sequence !== epoch.current) return;
      const exact = (
        missing ? missingBindingRetirementReview : bindingRetirementReview
      )(response, context, original);
      if (response.ok && !exact) response = checkoutFailure();
      setResult(response);
      if (exact) {
        setRetirement(exact);
        setMissingRetirement(missing);
      }
    } finally {
      if (active.current && sequence === epoch.current) setBusy(false);
    }
  }

  async function applyRetirement() {
    if (
      !retirement ||
      !selected ||
      !reader ||
      !confirmed ||
      busy ||
      locationBusy ||
      switching
    )
      return;
    const exact = retirement,
      original = selected,
      sequence = ++epoch.current;
    setBusy(true);
    setConfirmed(false);
    try {
      let response = await (missingRetirement
        ? cmdMissingBindingRetirementApply
        : cmdBindingRetirementApply)(exact.plan, exact.digest, true);
      if (!active.current || sequence !== epoch.current) return;
      if (
        response.ok &&
        (!(
          missingRetirement
            ? missingBindingRetirementReceipt
            : bindingRetirementReceipt
        )(response.data, original) ||
          response.data?.plan_digest !== exact.digest ||
          response.data?.operation_id !== exact.plan.operation_id)
      )
        response = checkoutFailure();
      setResult(response);
      if (response.ok) {
        setSelected({ ...original, binding_retirement: response.data });
        setRetirement(null);
      }
    } finally {
      if (active.current && sequence === epoch.current) setBusy(false);
    }
  }
  async function prepare(action: "confirm" | "adopt") {
    if (
      !review ||
      !reader ||
      !context ||
      nextReview ||
      busy ||
      locationBusy ||
      switching
    )
      return;
    const source = review,
      snapshot = record(record(source.plan.change).snapshot);
    const request =
      source.action === "request"
        ? source.plan.operation_id
        : record(source.plan.change).request_operation_id;
    if (
      typeof request !== "string" ||
      (action === "confirm" &&
        record(snapshot.context).context_id !== context.id)
    )
      return;
    const sequence = ++epoch.current;
    setBusy(true);
    setConfirmed(false);
    try {
      const values: Record<string, string> = { "request-operation": request };
      if (action === "adopt") {
        values.context = reader;
        values.root = root;
      }
      if (git.trim()) values["git-executable"] = git;
      let response = await cliPlan(
        `corporate project link-${action} plan`,
        values,
      );
      if (!active.current || sequence !== epoch.current) return;
      const exact = checkoutReview(
        response,
        action,
        context,
        String(record(snapshot.target).remote_project_id),
        snapshot,
        request,
      );
      if (response.ok && !exact) response = checkoutFailure();
      setResult(response);
      if (exact) setNextReview(exact);
    } finally {
      if (active.current && sequence === epoch.current) setBusy(false);
    }
  }

  async function applyNext() {
    if (
      !nextReview ||
      !reader ||
      !confirmed ||
      busy ||
      locationBusy ||
      switching
    )
      return;
    const exact = nextReview,
      sequence = ++epoch.current;
    setBusy(true);
    setConfirmed(false);
    try {
      let response = await cmdCheckoutApply(
        exact.plan,
        exact.digest,
        true,
        reader,
        git.trim() ? git : undefined,
      );
      if (!active.current || sequence !== epoch.current) return;
      if (response.ok && !checkoutReceipt(response, exact))
        response = checkoutFailure();
      setResult(response);
      if (response.ok) {
        setSelected(record(response.data));
        setReview(exact);
        setNextReview(null);
      }
    } finally {
      if (active.current && sequence === epoch.current) setBusy(false);
    }
  }
  async function reconcile() {
    if (!review || !reader || !confirmed || busy || locationBusy || switching)
      return;
    const exact = review,
      sequence = ++epoch.current;
    setBusy(true);
    setConfirmed(false);
    try {
      let response = await cmdCheckoutApply(
        exact.plan,
        exact.digest,
        true,
        reader,
      );
      if (!active.current || sequence !== epoch.current) return;
      if (
        response.ok &&
        (!retainedCheckout(response.data) ||
          response.data?.operation_id !== exact.plan.operation_id ||
          response.data?.plan_digest !== exact.digest)
      )
        response = checkoutFailure();
      setResult(response);
      if (response.ok) setSelected(record(response.data));
    } finally {
      if (active.current && sequence === epoch.current) setBusy(false);
    }
  }

  const locked = busy || locationBusy || switching;
  return (
    <section
      className="card space-y-4 p-5"
      aria-label={msg("checkoutOperations.corporateCheckoutHistory")}
    >
      <h2 className="section-title">
        {msg("checkoutOperations.corporateCheckoutOperations")}
      </h2>
      <p className="text-sm text-muted-foreground">
        {msg(
          "checkoutOperations.originalRequestsAndConfirmationsAcrossSavedViewsStayIn",
        )}
      </p>
      <button
        type="button"
        className="btn-outline"
        disabled={locked}
        onClick={() => void load()}
      >
        {msg("checkoutOperations.readCheckoutHistory")}
      </button>
      {busy && (
        <Spinner
          label={msg("checkoutOperations.readingTheOriginalCheckoutOperation")}
        />
      )}
      {!busy && !supported && (
        <p className="text-sm text-muted-foreground">
          {msg("checkoutOperations.thisEngineDoesNotExposeCheckoutHistory")}
        </p>
      )}
      {supported && rows.length === 0 && !busy && (
        <p>{msg("checkoutOperations.noRetainedCheckoutOperations")}</p>
      )}
      {rows.length > 0 && (
        <ul className="divide-y divide-border">
          {rows.map((item) => {
            const snapshot = record(record(record(item.plan).change).snapshot);
            return (
              <li className="space-y-2 py-3" key={String(item.operation_id)}>
                <p className="text-sm font-medium">
                  {scalarText(
                    record(snapshot.context).label ??
                      msg("checkoutOperations.originalContext"),
                  )}{" "}
                  · {String(item.state)}
                </p>
                <p className="text-xs break-all text-muted-foreground">
                  {scalarText(record(snapshot.account).origin ?? "")} ·{" "}
                  {scalarText(record(snapshot.target).remote_project_id ?? "")}
                </p>
                <button
                  type="button"
                  className="btn-outline"
                  disabled={locked}
                  onClick={() => void inspect(String(item.operation_id))}
                >
                  {msg("checkoutOperations.inspect")}{" "}
                  {String(item.operation_id)}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {cursor && (
        <button
          type="button"
          className="btn-outline"
          disabled={locked}
          onClick={() => void load(cursor)}
        >
          {msg("checkoutOperations.readMoreCheckoutHistory")}
        </button>
      )}
      {result && <ResultMeta r={result} />}
      {review && selected && (
        <section
          className="space-y-3"
          aria-label={msg("checkoutOperations.originalCheckoutOperation")}
        >
          <p className="font-mono text-xs break-all">
            {String(review.plan.operation_id)} · {review.digest}
          </p>
          <Details
            label={msg("checkoutOperations.originalCheckoutJournal")}
            value={selected}
          />
          {["applying", "interrupted"].includes(String(selected.state)) && (
            <>
              <p className="text-sm text-muted-foreground">
                {msg(
                  "checkoutOperations.reconciliationReadsTheOriginalOutcomeThroughAMatchingCurrent",
                )}
              </p>
              {!reader && (
                <p>
                  {msg(
                    "checkoutOperations.selectACurrentContextForTheSameAccountAnd",
                  )}
                </p>
              )}
              <label className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={!reader || locked}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                {msg(
                  "checkoutOperations.iReviewedThisOriginalIntentAndAuthorizeOutcomeReconciliation",
                )}
              </label>
              <button
                type="button"
                className="btn-primary"
                disabled={!reader || !confirmed || locked}
                onClick={() => void reconcile()}
              >
                {msg("checkoutOperations.reconcileOriginalOutcome")}
              </button>
            </>
          )}
          {selected.state === "completed" &&
            review.action !== "adopt" &&
            !nextReview && (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  {msg(
                    "checkoutOperations.continueTheOriginalRequestWithAFreshNativeReview",
                  )}
                </p>
                <label className="field-label">
                  {msg("checkoutOperations.registeredCheckoutForBinding")}
                  <input
                    className="input"
                    value={root}
                    disabled={locked}
                    onChange={(event) => setRoot(event.target.value)}
                  />
                </label>
                <label className="field-label">
                  {msg(
                    "checkoutOperations.trustedGitExecutableForCheckoutReviewOptional",
                  )}
                  <input
                    className="input"
                    value={git}
                    disabled={locked}
                    onChange={(event) => setGit(event.target.value)}
                  />
                </label>
                {review.action === "request" && (
                  <button
                    type="button"
                    className="btn-outline"
                    disabled={
                      !reader ||
                      locked ||
                      record(
                        record(record(review.plan.change).snapshot).context,
                      ).context_id !== context?.id
                    }
                    onClick={() => void prepare("confirm")}
                  >
                    {msg("checkoutOperations.reviewOriginalConfirmation")}
                  </button>
                )}
                <button
                  type="button"
                  className="btn-outline"
                  disabled={!reader || !root.trim() || locked}
                  onClick={() => void prepare("adopt")}
                >
                  {msg("checkoutOperations.reviewOriginalLocalBinding")}
                </button>
              </div>
            )}
          {selected.state === "completed" && review.action === "adopt" && (
            <div className="space-y-3">
              <CheckoutLocation
                key={`${context?.id}:${scalarText(review.plan.operation_id)}`}
                original={selected}
                context={context}
                reader={reader}
                disabled={busy || switching || !!retirement}
                onBusyChange={setLocationBusy}
              />
              {selected.binding_retirement != null ? (
                <>
                  <p role="status">
                    {msg(
                      "checkoutOperations.thisOriginalLocalBindingWasRetiredItsAdoptionReceipt",
                    )}
                  </p>
                  <Details
                    label={msg(
                      "checkoutOperations.verifiedLocalBindingRetirement",
                    )}
                    value={selected.binding_retirement}
                  />
                </>
              ) : (
                <>
                  <p role="status">
                    {msg(
                      "checkoutOperations.originalCorporateProjectBindingReceiptSaved",
                    )}
                  </p>
                  {retirementSupported &&
                    selected.binding_retirement === null &&
                    !retirement && (
                      <>
                        <p className="text-sm text-muted-foreground">
                          {msg(
                            "checkoutOperations.afterThisExactLinkIsUnlinkedOnTheServer",
                          )}
                        </p>
                        <button
                          type="button"
                          className="btn-outline"
                          disabled={!reader || locked}
                          onClick={() => void prepareRetirement()}
                        >
                          {msg(
                            "checkoutOperations.reviewLocalBindingRetirement",
                          )}
                        </button>
                      </>
                    )}
                </>
              )}
              {missingSupported &&
                selected.binding_retirement === null &&
                !retirement && (
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">
                      {msg(
                        "checkoutOperations.ifTheRetainedCheckoutNameIsAbsentSeparatelyReview",
                      )}
                    </p>
                    <button
                      type="button"
                      className="btn-outline"
                      disabled={!reader || locked}
                      onClick={() => void prepareRetirement(true)}
                    >
                      {msg(
                        "checkoutOperations.reviewMissingCheckoutBindingRetirement",
                      )}
                    </button>
                  </div>
                )}
              {retirement && (
                <section
                  className="space-y-3"
                  aria-label={msg(
                    "checkoutOperations.reviewLocalBindingRetirement",
                  )}
                >
                  <h3 className="font-medium">
                    {missingRetirement
                      ? msg(
                          "checkoutOperations.releaseThisAbsentCheckoutBinding",
                        )
                      : msg(
                          "checkoutOperations.releaseOnlyThisOriginalLocalBinding",
                        )}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {msg(
                      "checkoutOperations.theCliObservedTheExactServerLinkAsUnlinked",
                    )}
                  </p>
                  {missingRetirement && (
                    <p role="status">
                      {msg(
                        "checkoutOperations.theRetainedCheckoutNameWasAbsentUnderTheReviewed",
                      )}
                    </p>
                  )}
                  <p className="text-sm">
                    {msg("checkoutOperations.reviewedCheckoutDirectory")}
                  </p>
                  <p className="font-mono text-xs break-all">
                    {checkoutPath(
                      record(record(retirement.plan.snapshot).binding)
                        .checkout_root,
                    )}
                  </p>
                  <p className="font-mono text-xs break-all">
                    {retirement.digest}
                  </p>
                  <Details
                    label={msg(
                      "checkoutOperations.exactLocalBindingRetirementPlan",
                    )}
                    value={retirement.plan}
                  />
                  <label className="flex items-start gap-3 text-sm">
                    <input
                      type="checkbox"
                      checked={confirmed}
                      disabled={!reader || locked}
                      onChange={(event) => setConfirmed(event.target.checked)}
                    />
                    {msg(
                      "checkoutOperations.iReviewedThisExactLocalBindingRetirementAndAuthorize",
                    )}
                  </label>
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={!reader || !confirmed || locked}
                    onClick={() => void applyRetirement()}
                  >
                    {msg(
                      "checkoutOperations.applyReviewedLocalBindingRetirement",
                    )}
                  </button>
                  <p className="text-xs text-muted-foreground">
                    {msg(
                      "checkoutOperations.ifTheReplyIsUnconfirmedInspectThisOriginalOperation",
                    )}
                  </p>
                </section>
              )}
            </div>
          )}
          {nextReview && (
            <section
              className="space-y-3"
              aria-label={msg(
                "checkoutOperations.reviewRetainedCheckoutNextChange",
              )}
            >
              <h3 className="font-medium">
                {msg("checkoutOperations.reviewOriginal", {
                  action: nextReview.action,
                })}
              </h3>
              <p className="font-mono text-xs break-all">{nextReview.digest}</p>
              <Details
                label={msg("checkoutOperations.exactRetainedCheckoutNextPlan")}
                value={nextReview.plan}
              />
              <label className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={!reader || locked}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                {msg(
                  "checkoutOperations.iReviewedThisExactRetainedCheckoutChangeAndAuthorize",
                )}
              </label>
              <button
                type="button"
                className="btn-primary"
                disabled={!reader || !confirmed || locked}
                onClick={() => void applyNext()}
              >
                {msg("checkoutOperations.applyReviewedOriginalCheckoutChange")}
              </button>
            </section>
          )}
        </section>
      )}
    </section>
  );
}
