import { useText } from "../i18n";
import { useLayoutEffect, useRef, useState } from "react";
import { record, records, type ContextView } from "../contexts";
import { cliPlan, cmdCheckoutApply, type CmdResult } from "../transport";
import {
  checkoutFailure,
  checkoutPath,
  checkoutReceipt,
  checkoutReview,
  type CheckoutAction,
  type CheckoutReview,
} from "../checkoutLinks";
import { Link } from "react-router";
import { Details, ResultMeta, Spinner } from "./Result";

function refused(): CmdResult {
  return {
    ok: false,
    data: null,
    warnings: [],
    continuations: [],
    error:
      "The checkout preview does not match this company and project. Read it again.",
    error_code: "CONTEXT_VIEW",
  };
}

export default function CheckoutPreview({
  context,
  project,
  disabled,
  linking = false,
}: {
  context: ContextView;
  project: { id: string; name: string };
  disabled: boolean;
  linking?: boolean;
}) {
  const msg = useText();
  const [root, setRoot] = useState("");
  const [git, setGit] = useState("");
  const [provider, setProvider] = useState("");
  const [providers, setProviders] = useState<Record<string, unknown>[]>([]);
  const [result, setResult] = useState<CmdResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [review, setReview] = useState<CheckoutReview | null>(null);
  const [operationResult, setOperationResult] = useState<CmdResult | null>(
    null,
  );
  const [confirmed, setConfirmed] = useState(false);
  const [request, setRequest] = useState<string | null>(null);
  const [phase, setPhase] = useState<CheckoutAction | null>(null);
  const epoch = useRef(0);
  const active = useRef(false);
  useLayoutEffect(() => {
    active.current = true;
    epoch.current++;
    return () => {
      active.current = false;
      epoch.current++;
    };
  }, []);

  async function reviewLink(action: CheckoutAction) {
    if (
      !linking ||
      disabled ||
      busy ||
      !result?.ok ||
      context.mode !== "corporate"
    )
      return;
    const sequence = ++epoch.current;
    setBusy(true);
    setReview(null);
    setConfirmed(false);
    setOperationResult(null);
    const values: Record<string, string> =
      action === "request"
        ? { context: context.id, project: project.id, root }
        : { "request-operation": request ?? "" };
    if (action === "adopt") {
      values.context = context.id;
      values.root = root;
    }
    if (git.trim()) values["git-executable"] = git;
    if (action === "request" && provider) values["provider-project"] = provider;
    try {
      let response = await cliPlan(
        `corporate project link-${action} plan`,
        values,
      );
      if (!active.current || sequence !== epoch.current) return;
      const exact = checkoutReview(
        response,
        action,
        context,
        project.id,
        record(result.data?.preview),
        request ?? undefined,
      );
      if (response.ok && !exact) response = checkoutFailure();
      setOperationResult(response);
      if (exact) setReview(exact);
    } finally {
      if (active.current && sequence === epoch.current) setBusy(false);
    }
  }

  async function applyLink() {
    if (!review || !confirmed || disabled || busy) return;
    const exact = review,
      sequence = ++epoch.current;
    setBusy(true);
    setConfirmed(false);
    if (exact.action === "request") setRequest(String(exact.plan.operation_id));
    try {
      let response = await cmdCheckoutApply(
        exact.plan,
        exact.digest,
        true,
        context.id,
        git.trim() ? git : undefined,
      );
      if (!active.current || sequence !== epoch.current) return;
      if (response.ok && !checkoutReceipt(response, exact))
        response = checkoutFailure();
      setOperationResult(response);
      if (response.ok) {
        setPhase(exact.action);
        setReview(null);
      }
    } finally {
      if (active.current && sequence === epoch.current) setBusy(false);
    }
  }

  async function preview() {
    if (disabled || busy || context.mode !== "corporate" || !root.trim())
      return;
    const sequence = ++epoch.current;
    const values: Record<string, string> = {
      context: context.id,
      project: project.id,
      root,
    };
    if (git.trim()) values["git-executable"] = git;
    if (provider) values["provider-project"] = provider;
    setBusy(true);
    setResult(null);
    try {
      let response = await cliPlan("corporate project link-preview", values);
      if (!active.current || sequence !== epoch.current) return;
      const data = record(response.data?.preview);
      const target = record(data.target);
      const account = record(data.account);
      const authority = record(record(data.context).authority);
      if (
        response.ok &&
        (record(data.context).context_id !== context.id ||
          account.origin !== context.origin ||
          (record(account.connection).connection_id ?? null) !==
            context.connection ||
          target.remote_project_id !== project.id ||
          record(data.request_coordinates).remote_project_id !== project.id ||
          record(data.request_coordinates).provider_project_id !==
            (provider || null) ||
          (record(data.selected_provider).provider_project_id ?? null) !==
            (provider || null) ||
          target.organization_id !==
            record(authority.organization).organization_id ||
          data.observation_only !== true ||
          data.online_verified !== true ||
          data.link_created !== false ||
          data.binding_created !== false ||
          data.request_admitted !== false ||
          data.installation_authority !== false)
      )
        response = refused();
      setResult(response);
      // These are choices for a new checked preview, never a cached grant.
      if (response.ok) setProviders(records(target.providers));
      else {
        setProviders([]);
        setProvider("");
      }
    } finally {
      if (active.current && sequence === epoch.current) setBusy(false);
    }
  }

  const data = record(result?.data?.preview);
  const checkout = record(record(data.checkout).checkout);
  const local = record(data.local_project);
  const observedRoot = checkoutPath(record(local.root).path);
  return (
    <section
      className="card space-y-4"
      aria-label={msg("checkoutPreview.corporateCheckoutPreview")}
    >
      <div className="space-y-2">
        <h2 className="section-title">
          {msg("checkoutPreview.reviewCheckoutFor")} {project.name}
        </h2>
        <p className="text-sm text-muted-foreground">
          {msg(
            "checkoutPreview.chooseAnExistingRegisteredProjectWithACommittedGit",
          )}
        </p>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void preview();
        }}
      >
        <fieldset
          disabled={busy || disabled || review !== null || request !== null}
          className="space-y-4"
        >
          <label className="field-label">
            {msg("checkoutPreview.checkoutDirectory")}
            <input
              className="input"
              required
              value={root}
              onChange={(event) => {
                setRoot(event.target.value);
                setResult(null);
                setProviders([]);
                setProvider("");
              }}
            />
          </label>
          <label className="field-label">
            {msg("checkoutPreview.gitExecutableOptional")}
            <input
              className="input"
              value={git}
              onChange={(event) => {
                setGit(event.target.value);
                setResult(null);
                setProviders([]);
                setProvider("");
              }}
            />
          </label>
          <p className="field-help">
            {msg("checkoutPreview.useAnAbsolutePathToAnExistingTrustedGit")}
          </p>
          {providers.length > 0 && (
            <label className="field-label">
              {msg("checkoutPreview.corporateRepositoryOptional")}
              <select
                className="input"
                value={provider}
                onChange={(event) => {
                  setProvider(event.target.value);
                  setResult(null);
                }}
              >
                <option value="">
                  {msg("checkoutPreview.noRepositoryAssertion")}
                </option>
                {providers.map((item) => (
                  <option
                    key={String(item.provider_project_id)}
                    value={String(item.provider_project_id)}
                  >
                    {String(item.provider)} {msg("checkoutPreview.repository")}{" "}
                    {String(item.immutable_repository_id)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button className="btn-primary" type="submit" disabled={!root.trim()}>
            {msg("checkoutPreview.previewCheckout")}
          </button>
        </fieldset>
      </form>
      {busy && (
        <Spinner
          label={msg("checkoutPreview.checkingCheckoutAndCurrentCompanyAccess")}
        />
      )}
      {result && <ResultMeta r={result} />}
      {result?.ok && (
        <div
          className="space-y-3"
          aria-label={msg("checkoutPreview.verifiedCheckoutObservation")}
        >
          <h3 className="font-medium">
            {msg("checkoutPreview.checkoutVerifiedForReview")}
          </h3>
          {typeof observedRoot === "string" && (
            <p className="break-all text-sm">{observedRoot}</p>
          )}
          <p className="break-all font-mono text-xs text-muted-foreground">
            {msg("checkoutPreview.commit")} {String(checkout.commit ?? "")}
          </p>
          <p className="text-sm text-muted-foreground">
            {msg(
              "checkoutPreview.previewOnlySavingAProjectLinkRequiresASeparate",
            )}
          </p>
          <Details
            label={msg("checkoutPreview.checkoutObservationEvidence")}
            value={result.data}
          />
          {linking && !review && phase !== "adopt" && (
            <button
              className="btn-primary"
              disabled={busy || disabled}
              onClick={() =>
                void reviewLink(
                  phase === "request"
                    ? "confirm"
                    : phase === "confirm"
                      ? "adopt"
                      : "request",
                )
              }
            >
              {phase === "request"
                ? msg("checkoutPreview.reviewLinkConfirmation")
                : phase === "confirm"
                  ? msg("checkoutPreview.reviewLocalBinding")
                  : msg("checkoutPreview.reviewLinkRequest")}
            </button>
          )}
        </div>
      )}
      {review && (
        <section
          className="space-y-4"
          aria-label={msg("checkoutPreview.reviewCorporateCheckoutChange")}
        >
          <h3 className="section-title">
            {msg("checkoutPreview.review")}{" "}
            {review.action === "request"
              ? msg("checkoutPreview.serverPlanRequest")
              : review.action === "confirm"
                ? msg("checkoutPreview.projectLinkConfirmation")
                : msg("checkoutPreview.localProjectBinding")}
          </h3>
          <p className="text-sm text-muted-foreground">
            {msg(
              "checkoutPreview.thisOperationRetainsItsOriginalCompanyAndCheckoutIt",
            )}
          </p>
          <p className="break-all font-mono text-xs">{review.digest}</p>
          <Details
            label={msg("checkoutPreview.exactCheckoutPlan")}
            value={review.plan}
          />
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={busy || disabled}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            {msg(
              "checkoutPreview.iReviewedThisExactCheckoutPlanAndAuthorizeIts",
            )}
          </label>
          <button
            className="btn-primary"
            disabled={busy || disabled || !confirmed}
            onClick={() => void applyLink()}
          >
            {msg("checkoutPreview.applyReviewedCheckoutChange")}
          </button>
          {!request && (
            <button
              className="btn-outline"
              disabled={busy}
              onClick={() => {
                setReview(null);
                setConfirmed(false);
              }}
            >
              {msg("checkoutPreview.dismissCheckoutReview")}
            </button>
          )}
        </section>
      )}
      {operationResult && <ResultMeta r={operationResult} />}
      {request && (
        <div
          className="space-y-2"
          aria-label={msg("checkoutPreview.retainedCheckoutOperation")}
        >
          <p className="break-all font-mono text-xs">
            {msg("checkoutPreview.originalRequest")} {request}
          </p>
          {phase === "adopt" ? (
            <p role="status">
              {msg("checkoutPreview.corporateProjectBindingSaved")}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              {msg("checkoutPreview.ifAReplyIsUnconfirmedOrTheAppCloses")}
            </p>
          )}
          <Link className="text-sm text-primary" to="/tasks">
            {msg("checkoutPreview.openActivity")}
          </Link>
        </div>
      )}
    </section>
  );
}
