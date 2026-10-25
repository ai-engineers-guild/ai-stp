import { useEffect, useRef, useState } from "react";
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
  async function refresh() {
    const epoch = ++readEpoch.current;
    const [connections, contexts] = await Promise.all([
      cmdRunRead("account connections list"),
      cmdRunRead("context list"),
    ]);
    if (active.current && epoch === readEpoch.current) {
      setConnections(connections);
      setContexts(contexts);
    }
  }
  useEffect(() => {
    active.current = true;
    void refresh();
    return () => {
      active.current = false;
      readEpoch.current++;
    };
  }, []);
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
        eyebrow="System"
        title="Connections and contexts"
        description="Keep personal and company sessions together. Selecting a view preserves credentials, unfinished operations and installed harness files."
        action={
          <button
            className="btn-outline"
            disabled={busy}
            onClick={() => void refresh()}
          >
            Refresh local records
          </button>
        }
      />
      <section className="card space-y-4 p-6">
        <h2 className="section-title">Retained connections</h2>
        <Link className="btn-outline" to="/auth">
          Local-owner account session
        </Link>
        {!connections && <Spinner label="Reading local connections" />}
        {connections && !connections.ok && (
          <>
            <ResultMeta r={connections} />
            <Link className="btn-outline" to="/settings">
              Check local initialization
            </Link>
          </>
        )}
        {connections?.ok && !retained.length && (
          <p>No retained connections yet.</p>
        )}
        {retained.map((item) => (
          <div
            className="space-y-2 rounded-lg border border-border p-4"
            key={String(item.connection_id)}
          >
            <h3 className="font-medium">{String(item.label)}</h3>
            <p className="break-all text-sm text-muted-foreground">
              {String(item.origin)} · {String(item.provider)} ·{" "}
              {String(item.state)}
            </p>
            {item.state === "ready" ? (
              <Link
                className="btn-outline"
                to={`/auth?connection=${encodeURIComponent(String(item.connection_id))}`}
              >
                Open this account session
              </Link>
            ) : (
              <button
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
                Review interrupted creation
              </button>
            )}
          </div>
        ))}
      </section>
      <section className="card space-y-4 p-6">
        <h2 className="section-title">Add a connection</h2>
        <p className="text-sm text-muted-foreground">
          Each connection gets its own server enrollment key in your selected
          credential store. Existing keys and sessions stay available.
        </p>
        <label className="field-label">
          Connection label
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
          Server origin
          <input
            className="input"
            type="url"
            placeholder="https://your-server.example"
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
          className="btn-outline"
          disabled={busy || !origin.trim()}
          onClick={() => void checkServer()}
        >
          Check server sign-in methods
        </button>
        {discovery && <ResultMeta r={discovery} />}
        {discovery?.ok && !providers.length && (
          <p role="status">
            No sign-in methods supported by this engine are enabled on this
            server.
          </p>
        )}
        {!!providers.length && (
          <label className="field-label">
            Sign-in method
            <select
              className="input"
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
          Review connection creation
        </button>
      </section>
      <section className="card space-y-4 p-6">
        <h2 className="section-title">Context views</h2>
        <p className="text-sm text-muted-foreground">
          These are retained observations and a selected view preference.
          Current access requires an online check; selection does not activate a
          harness configuration or retarget an existing plan.
        </p>
        {!contexts && <Spinner label="Reading context views" />}
        {contexts && !contexts.ok && <ResultMeta r={contexts} />}
        {contexts?.ok && !items(contexts.data?.contexts).length && (
          <p>No saved contexts yet.</p>
        )}
        {items(contexts?.data?.contexts).map((item) => {
          const context = object(item.context),
            authority = object(context.authority),
            org = object(authority.organization);
          return (
            <div
              className="space-y-2 rounded-lg border border-border p-4"
              key={String(context.context_id)}
            >
              <h3 className="font-medium">
                {String(context.label)}
                {selected === context.context_id ? " · Selected view" : ""}
              </h3>
              <p className="text-sm text-muted-foreground">
                {authority.kind === "local"
                  ? "Personal · Native offline"
                  : `${String(org.kind)} · ${String(org.display_name)} · Cached observation`}
              </p>
              <button
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
                Review view selection
              </button>
              {authority.kind === "remote" && (
                <button
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
                  Check current access
                </button>
              )}
            </div>
          );
        })}
        <label className="field-label">
          Context label
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
          Context connection
          <select
            className="input"
            value={connection}
            disabled={busy}
            onChange={(e) => {
              setConnection(e.target.value);
              setOrganizations(null);
              setOrganization("");
              clearReview();
            }}
          >
            <option value="">Personal · Native offline</option>
            <option value="legacy-account">
              Existing local-owner account session
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
            className="btn-outline"
            disabled={busy}
            onClick={() => void readOrganizations()}
          >
            Read available organizations
          </button>
        )}
        {organizations && !organizations.ok && <ResultMeta r={organizations} />}
        {legacy && (
          <Link className="btn-outline" to="/auth">
            Check existing account sign-in
          </Link>
        )}
        {!!availableOrganizations.length && (
          <label className="field-label">
            Organization
            <select
              className="input"
              value={organization}
              disabled={busy}
              onChange={(e) => {
                setOrganization(e.target.value);
                clearReview();
              }}
            >
              <option value="">Choose an organization</option>
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
          Review context creation
        </button>
      </section>
      {review && (
        <section
          className="card space-y-4 p-6"
          aria-label="Review native profile plan"
        >
          <h2 className="section-title">Review the exact change</h2>
          <p className="text-sm">
            Creating the first connection or context explicitly upgrades the
            shared authority registry to format 55. Older clients will refuse
            that format. Preserve a compatible client for continued access.
          </p>
          <p className="break-all font-mono text-xs">{review.digest}</p>
          <Details label="Exact public plan" value={review.plan} />
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={busy}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I reviewed this exact plan and authorize this local change.
          </label>
          <button
            className="btn-primary"
            disabled={busy || !confirmed}
            onClick={() => void apply()}
          >
            Apply reviewed change
          </button>
          <button className="btn-outline" disabled={busy} onClick={clearReview}>
            Dismiss review
          </button>
        </section>
      )}
      {busy && <Spinner label="Working through the native engine" />}
      {result && (
        <>
          <ResultMeta r={result} />
          <Details label="Public operation result" value={result.data} />
        </>
      )}
    </div>
  );
}
