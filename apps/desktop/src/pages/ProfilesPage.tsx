import { useText } from "../i18n";
import { useCallback, useEffect, useRef, useState } from "react";
import { useContexts } from "../contexts";
import { Link } from "react-router";
import {
  cliPlan,
  cmdMachineHelp,
  cmdProfileApply,
  cmdRunRead,
  descriptorChoices,
  type CmdResult,
} from "../transport";
import { Details, ResultMeta, Spinner } from "../components/Result";
import { PageHeader } from "../components/Layout";

type ObjectValue = Record<string, unknown>;
const object = (value: unknown): ObjectValue =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as ObjectValue)
    : {};
const items = (value: unknown): ObjectValue[] =>
  Array.isArray(value) ? value.map(object) : [];
type Review = {
  path: "account connections apply" | "context apply";
  plan: unknown;
  digest: string;
};

export default function ProfilesPage() {
  const msg = useText();
  const [connections, setConnections] = useState<CmdResult | null>(null);
  const [contexts, setContexts] = useState<CmdResult | null>(null);
  const [label, setLabel] = useState("");
  const [origin, setOrigin] = useState("");
  const originRef = useRef(origin);
  originRef.current = origin;
  const [provider, setProvider] = useState("");
  const [providers, setProviders] = useState<string[]>([]);
  const [discovery, setDiscovery] = useState<CmdResult | null>(null);
  const [checkedOrigin, setCheckedOrigin] = useState("");
  const [contextLabel, setContextLabel] = useState("");
  const [connection, setConnection] = useState("");
  const connectionRef = useRef(connection);
  connectionRef.current = connection;
  const [organizations, setOrganizations] = useState<CmdResult | null>(null);
  const [organization, setOrganization] = useState("");
  const [result, setResult] = useState<CmdResult | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const active = useRef(true);
  const readEpoch = useRef(0);
  const refresh = useCallback(async () => {
    const epoch = ++readEpoch.current;
    const [connections, contexts] = await Promise.all([
      cmdRunRead("account connections list"),
      cmdRunRead("context list"),
    ]);
    if (active.current && epoch === readEpoch.current) {
      setConnections(connections);
      setContexts(contexts);
    }
  }, []);
  useEffect(() => {
    active.current = true;
    void refresh();
    return () => {
      active.current = false;
      readEpoch.current++;
    };
  }, [refresh]);
  function clearReview() {
    setReview(null);
    setConfirmed(false);
  }
  async function checkServer() {
    const selected = origin;
    setBusy(true);
    setProviders([]);
    setDiscovery(null);
    clearReview();
    try {
      const [help, response] = await Promise.all([
        cmdMachineHelp(),
        cmdRunRead("account providers", { "api-url": selected }),
      ]);
      if (!active.current || originRef.current !== selected) return;
      const allowed = help.ok
        ? (descriptorChoices(help, "account connections plan", "provider") ??
          [])
        : [];
      const available = Array.isArray(response.data?.providers)
        ? response.data.providers
        : [];
      const choices = allowed.filter((value) => available.includes(value));
      setDiscovery(response.ok && !help.ok ? help : response);
      setCheckedOrigin(selected);
      setProviders(choices);
      setProvider(choices[0] ?? "");
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function plan(
    path: string,
    values: Record<string, string>,
    apply: Review["path"],
    flags: string[] = [],
  ) {
    if (busy) return;
    setBusy(true);
    clearReview();
    try {
      const response = flags.length
        ? await cliPlan(path, values, flags)
        : await cliPlan(path, values);
      if (!active.current) return;
      setResult(response);
      if (
        response.ok &&
        response.data?.plan &&
        typeof response.data.plan_digest === "string"
      ) {
        setReview({
          path: apply,
          plan: response.data.plan,
          digest: response.data.plan_digest,
        });
      }
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function apply() {
    if (!review || !confirmed || busy) return;
    const exact = review;
    setBusy(true);
    try {
      const response = await cmdProfileApply(
        exact.path,
        exact.plan,
        exact.digest,
        true,
      );
      if (response.ok) await useContexts.getState().refresh(true);
      if (!active.current) return;
      setResult(response);
      if (response.ok) clearReview();
      await refresh();
    } finally {
      if (active.current) setBusy(false);
    }
  }
  async function readOrganizations() {
    if (!connection || busy) return;
    const selected = connection;
    setBusy(true);
    setOrganizations(null);
    setOrganization("");
    clearReview();
    try {
      const response =
        selected === "legacy-account"
          ? await cmdRunRead("account organizations", {}, ["legacy-account"])
          : await cmdRunRead("account organizations", { connection: selected });
      if (active.current && connectionRef.current === selected) {
        setOrganizations(response);
      }
    } finally {
      if (active.current) setBusy(false);
    }
  }
  const retained = items(connections?.data?.connections);
  const availableOrganizations = items(
    object(organizations?.data?.organizations).items,
  );
  const selected = object(contexts?.data?.selected).context_id;
  const legacy = connection === "legacy-account";
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={msg("profiles.system")}
        title={msg("profiles.connectionsAndContexts")}
        description={msg(
          "profiles.keepPersonalAndCompanySessionsTogetherSelectingAView",
        )}
        action={
          <button
            type="button"
            className="btn-outline"
            disabled={busy}
            onClick={() => void refresh()}
          >
            {msg("profiles.refreshLocalRecords")}
          </button>
        }
      />
      <section className="card space-y-4 p-6">
        <h2 className="section-title">{msg("profiles.retainedConnections")}</h2>
        <Link className="btn-outline" to="/auth">
          {msg("profiles.localOwnerAccountSession")}
        </Link>
        {!connections && (
          <Spinner label={msg("profiles.readingLocalConnections")} />
        )}
        {connections && !connections.ok && (
          <>
            <ResultMeta r={connections} />
            <Link className="btn-outline" to="/settings">
              {msg("profiles.checkLocalInitialization")}
            </Link>
          </>
        )}
        {connections?.ok && !retained.length && (
          <p>{msg("profiles.noRetainedConnectionsYet")}</p>
        )}
        {retained.map((item) => (
          <div
            className="space-y-2 rounded-lg border border-border p-4"
            key={String(item.connection_id)}
            role="group"
            aria-label={String(item.label)}
          >
            <h3 className="font-medium">{String(item.label)}</h3>
            <p className="text-sm break-all text-muted-foreground">
              {String(item.origin)} · {String(item.provider)} ·{" "}
              {String(item.state)}
            </p>
            {item.state === "ready" ? (
              <Link
                className="btn-outline"
                to={`/auth?connection=${encodeURIComponent(String(item.connection_id))}`}
              >
                {msg("profiles.openThisAccountSession")}
              </Link>
            ) : (
              <button
                type="button"
                className="btn-outline"
                disabled={busy}
                onClick={() => {
                  const pending = object(item.pending_operation);
                  if (typeof pending.plan_digest === "string") {
                    setReview({
                      path: "account connections apply",
                      plan: pending.plan,
                      digest: pending.plan_digest,
                    });
                    setConfirmed(false);
                  }
                }}
              >
                {msg("profiles.reviewInterruptedCreation")}
              </button>
            )}
          </div>
        ))}
      </section>
      <section className="card space-y-4 p-6">
        <h2 className="section-title">{msg("profiles.addAConnection")}</h2>
        <p className="text-sm text-muted-foreground">
          {msg("profiles.eachConnectionGetsItsOwnServerEnrollmentKeyIn")}
        </p>
        <label className="field-label">
          {msg("profiles.connectionLabel")}
          <input
            className="input"
            value={label}
            disabled={busy}
            maxLength={120}
            onChange={(e) => {
              setLabel(e.target.value);
              clearReview();
            }}
          />
        </label>
        <label className="field-label">
          {msg("profiles.serverOrigin")}
          <input
            className="input"
            type="url"
            placeholder={msg("profiles.httpsYourServerExample")}
            value={origin}
            disabled={busy}
            onChange={(e) => {
              setOrigin(e.target.value);
              setDiscovery(null);
              setProviders([]);
              clearReview();
            }}
          />
        </label>
        <button
          type="button"
          className="btn-outline"
          disabled={busy || !origin.trim()}
          onClick={() => void checkServer()}
        >
          {msg("profiles.checkServerSignInMethods")}
        </button>
        {discovery && <ResultMeta r={discovery} />}
        {discovery?.ok && !providers.length && (
          <p role="status">
            {msg("profiles.noSignInMethodsSupportedByThisEngineAre")}
          </p>
        )}
        {!!providers.length && (
          <label className="field-label">
            {msg("profiles.signInMethod")}
            <select
              className="input"
              aria-label={msg("profiles.signInMethod")}
              value={provider}
              disabled={busy}
              onChange={(e) => {
                setProvider(e.target.value);
                clearReview();
              }}
            >
              {providers.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
        )}
        <button
          type="button"
          className="btn-primary"
          disabled={
            busy ||
            !label.trim() ||
            !providers.includes(provider) ||
            checkedOrigin !== origin ||
            !discovery?.ok ||
            typeof discovery.data?.origin !== "string"
          }
          onClick={() =>
            void plan(
              "account connections plan",
              {
                label: label.trim(),
                "api-url": String(discovery?.data?.origin),
                provider,
              },
              "account connections apply",
            )
          }
        >
          {msg("profiles.reviewConnectionCreation")}
        </button>
      </section>
      <section className="card space-y-4 p-6">
        <h2 className="section-title">{msg("profiles.contextViews")}</h2>
        <p className="text-sm text-muted-foreground">
          {msg(
            "profiles.theseAreRetainedObservationsAndASelectedViewPreference",
          )}
        </p>
        {!contexts && <Spinner label={msg("profiles.readingContextViews")} />}
        {contexts && !contexts.ok && <ResultMeta r={contexts} />}
        {contexts?.ok && !items(contexts.data?.contexts).length && (
          <p>{msg("profiles.noSavedContextsYet")}</p>
        )}
        {items(contexts?.data?.contexts).map((item) => {
          const context = object(item.context),
            authority = object(context.authority),
            org = object(authority.organization);
          return (
            <div
              className="space-y-2 rounded-lg border border-border p-4"
              key={String(context.context_id)}
              role="group"
              aria-label={String(context.label)}
            >
              <h3 className="font-medium">
                {String(context.label)}
                {selected === context.context_id
                  ? msg("profiles.selectedView")
                  : ""}
              </h3>
              <p className="text-sm text-muted-foreground">
                {authority.kind === "local"
                  ? msg("profiles.personalNativeOffline")
                  : msg("profiles.cachedOrganization", {
                      kind: String(org.kind),
                      name: String(org.display_name),
                    })}
              </p>
              <button
                type="button"
                className="btn-outline"
                disabled={busy || selected === context.context_id}
                onClick={() =>
                  void plan(
                    "context select plan",
                    { context: String(context.context_id) },
                    "context apply",
                  )
                }
              >
                {msg("profiles.reviewViewSelection")}
              </button>
              {authority.kind === "remote" && (
                <button
                  type="button"
                  className="btn-outline"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      const response = await cmdRunRead(
                        "context show",
                        { context: String(context.context_id) },
                        ["refresh"],
                      );
                      if (active.current) setResult(response);
                    } finally {
                      if (active.current) setBusy(false);
                    }
                  }}
                >
                  {msg("profiles.checkCurrentAccess")}
                </button>
              )}
            </div>
          );
        })}
        <label className="field-label">
          {msg("profiles.contextLabel")}
          <input
            className="input"
            value={contextLabel}
            disabled={busy}
            maxLength={120}
            onChange={(e) => {
              setContextLabel(e.target.value);
              clearReview();
            }}
          />
        </label>
        <label className="field-label">
          {msg("profiles.contextConnection")}
          <select
            className="input"
            aria-label={msg("profiles.contextConnection")}
            value={connection}
            disabled={busy}
            onChange={(e) => {
              setConnection(e.target.value);
              setOrganizations(null);
              setOrganization("");
              clearReview();
            }}
          >
            <option value="">{msg("profiles.personalNativeOffline")}</option>
            <option value="legacy-account">
              {msg("profiles.existingLocalOwnerAccountSession")}
            </option>
            {retained
              .filter((item) => item.state === "ready")
              .map((item) => (
                <option
                  key={String(item.connection_id)}
                  value={String(item.connection_id)}
                >
                  {String(item.label)} · {String(item.origin)}
                </option>
              ))}
          </select>
        </label>
        {!!connection && (
          <button
            type="button"
            className="btn-outline"
            disabled={busy}
            onClick={() => void readOrganizations()}
          >
            {msg("profiles.readAvailableOrganizations")}
          </button>
        )}
        {organizations && !organizations.ok && <ResultMeta r={organizations} />}
        {legacy && (
          <Link className="btn-outline" to="/auth">
            {msg("profiles.checkExistingAccountSignIn")}
          </Link>
        )}
        {!!availableOrganizations.length && (
          <label className="field-label">
            {msg("profiles.organization")}
            <select
              className="input"
              aria-label={msg("profiles.organization")}
              value={organization}
              disabled={busy}
              onChange={(e) => {
                setOrganization(e.target.value);
                clearReview();
              }}
            >
              <option value="">{msg("profiles.chooseAnOrganization")}</option>
              {availableOrganizations.map((item) => (
                <option
                  key={String(item.organization_id)}
                  value={String(item.organization_id)}
                >
                  {String(item.display_name)} · {String(item.kind)}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          type="button"
          className="btn-primary"
          disabled={
            busy ||
            !contextLabel.trim() ||
            (!!connection &&
              !availableOrganizations.some(
                (item) => item.organization_id === organization,
              ))
          }
          onClick={() =>
            void plan(
              "context create plan",
              {
                label: contextLabel.trim(),
                ...(connection
                  ? { organization, ...(!legacy ? { connection } : {}) }
                  : {}),
              },
              "context apply",
              legacy ? ["legacy-account"] : [],
            )
          }
        >
          {msg("profiles.reviewContextCreation")}
        </button>
      </section>
      {review && (
        <section
          className="card space-y-4 p-6"
          aria-label={msg("profiles.reviewNativeProfilePlan")}
        >
          <h2 className="section-title">
            {msg("profiles.reviewTheExactChange")}
          </h2>
          <p className="text-sm">
            {typeof object(review.plan).registry_schema_after === "number"
              ? msg("profiles.registryFormat", {
                  version: Number(object(review.plan).registry_schema_after),
                })
              : msg("profiles.registryFormatUnknown")}
          </p>
          <p className="font-mono text-xs break-all">{review.digest}</p>
          <Details
            label={msg("profiles.exactPublicPlan")}
            value={review.plan}
          />
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={busy}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            {msg("profiles.iReviewedThisExactPlanAndAuthorizeThisLocal")}
          </label>
          <button
            type="button"
            className="btn-primary"
            disabled={busy || !confirmed}
            onClick={() => void apply()}
          >
            {msg("profiles.applyReviewedChange")}
          </button>
          <button
            type="button"
            className="btn-outline"
            disabled={busy}
            onClick={clearReview}
          >
            {msg("profiles.dismissReview")}
          </button>
        </section>
      )}
      {busy && (
        <Spinner label={msg("profiles.workingThroughTheNativeEngine")} />
      )}
      {result && (
        <>
          <ResultMeta r={result} />
          <Details
            label={msg("profiles.publicOperationResult")}
            value={result.data}
          />
        </>
      )}
    </div>
  );
}
