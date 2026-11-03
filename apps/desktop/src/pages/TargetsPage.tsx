import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useContexts, record, records } from "../contexts";
import { useApp } from "../store";
import {
  cliApplyConfirmed,
  cliPlan,
  cmdNativeConfigurationPlan,
  cmdNativeConfigurationPrepare,
  cmdRunRead,
  type CmdResult,
} from "../transport";
import {
  confirmationCommand,
  nativeArguments,
  nativePending,
  nativeReview,
  type NativeOperation,
} from "../nativeConfiguration";
import { Details, ResultMeta, Spinner } from "../components/Result";
import { EmptyState, PageHeader, StatusBadge } from "../components/Layout";

export default function TargetsPage() {
  const { selected, refresh: refreshContexts } = useContexts();
  const capabilities = useApp((state) => state.capabilities);
  const native = record(capabilities?.data?.native_configuration);
  const harnesses = Array.isArray(native.harnesses)
    ? native.harnesses.filter(
        (value): value is string => typeof value === "string",
      )
    : [];
  const [harness, setHarness] = useState("codex"),
    [setup, setSetup] = useState("");
  const [version, setVersion] = useState(""),
    [passport, setPassport] = useState("");
  const [globalRoot, setGlobalRoot] = useState(""),
    [userRoot, setUserRoot] = useState(""),
    [projectRoot, setProjectRoot] = useState("");
  const [binding, setBinding] = useState(""),
    [replace, setReplace] = useState(false),
    [trust, setTrust] = useState(false);
  const [result, setResult] = useState<CmdResult | null>(null),
    [effective, setEffective] = useState<CmdResult | null>(null);
  const [operation, setOperation] = useState<NativeOperation | null>(null),
    [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false);
  const [otherPending, setOtherPending] = useState(false);
  const epoch = useRef(0),
    alive = useRef(true);
  const operationRef = useRef(operation);
  operationRef.current = operation;
  async function refresh() {
    const current = ++epoch.current,
      context = selected?.id;
    const [owned, pending] = await Promise.all([
      context
        ? cmdRunRead("configuration native effective", { context })
        : Promise.resolve(null),
      cmdRunRead("configuration native pending"),
    ]);
    if (!alive.current || current !== epoch.current) return;
    setEffective(owned);
    setOtherPending(pending.data?.other_state_pending === true);
    const recovered = nativePending(pending);
    if (
      recovered &&
      (!operationRef.current ||
        operationRef.current.operation === recovered.operation)
    ) {
      setOperation({ ...recovered, plan: operationRef.current?.plan ?? null });
    }
  }
  useEffect(() => {
    alive.current = true;
    void refreshContexts();
    return () => {
      alive.current = false;
      epoch.current++;
    };
  }, []);
  useEffect(() => {
    if (native.available === true) void refresh();
  }, [selected?.id, native.available]);
  const active =
    operation &&
    ["prepared", "applying", "finishing"].includes(operation.phase);
  const editable = !busy && !active && !otherPending;
  async function review() {
    if (!selected || !editable) return;
    const context = selected.id;
    const roots: Record<string, string> = {};
    if (globalRoot) roots.global = globalRoot;
    if (userRoot) roots.user_root = userRoot;
    if (projectRoot) roots.project = projectRoot;
    setBusy(true);
    setConfirmed(false);
    try {
      const response = await cmdNativeConfigurationPlan(context, {
        schema_version: 1,
        setup: { stable_id: setup, version, passport_digest: passport },
        harness_id: harness,
        operation: replace ? "replace" : "install",
        roots,
        trust: trust ? "exact_setup" : "pinned",
        ...(binding ? { corporate_binding: binding } : {}),
      });
      if (!alive.current) return;
      setResult(response);
      setOperation(nativeReview(response));
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function prepare() {
    const held = operation;
    if (!held?.plan || !confirmed || busy) return;
    setBusy(true);
    try {
      const response = await cmdNativeConfigurationPrepare(
        held.plan,
        held.digest,
        true,
      );
      if (!alive.current) return;
      setResult(response);
      setConfirmed(false);
      if (response.ok) setOperation({ ...held, phase: "prepared" });
      await refresh();
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function run(action: "apply" | "cancel" | "status") {
    const held = operation;
    if (!held || busy) return;
    setBusy(true);
    try {
      const response =
        action === "status"
          ? await cmdRunRead(
              "configuration native status",
              nativeArguments(held),
            )
          : await cliApplyConfirmed(
              `configuration native ${action}`,
              nativeArguments(held),
              [],
              true,
            );
      if (!alive.current) return;
      setResult(response);
      if (response.ok)
        setOperation({
          ...held,
          phase:
            action === "apply"
              ? "configured"
              : action === "cancel"
                ? "cancelled"
                : String(response.data?.state ?? held.phase),
        });
      await refresh();
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function remove(item: Record<string, unknown>) {
    if (!editable) return;
    const values = {
      operation: String(item.operation_id ?? ""),
      "plan-digest": String(item.plan_digest ?? ""),
    };
    setBusy(true);
    setConfirmed(false);
    try {
      const response = await cliPlan(
        "configuration native remove plan",
        values,
      );
      if (alive.current) {
        setResult(response);
        setOperation(nativeReview(response));
      }
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  const contextChanged = operation && selected?.id !== operation.context;
  const confirmCommand = operation
    ? confirmationCommand(operation, String(capabilities?.data?.os ?? "linux"))
    : null;
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Workspace"
        title="Configuration targets"
        description="Review and apply exact setups. Harness executables stay under your control."
      />
      {native.available !== true ? (
        <EmptyState title="Native configuration unavailable">
          Use a CLI/Desktop pair with the qualified native configuration engine.
        </EmptyState>
      ) : (
        <>
          <section className="card p-5" aria-label="Effective setup">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Current context</h2>
              <button
                className="btn-secondary"
                disabled={busy}
                onClick={() => void refresh()}
              >
                Refresh
              </button>
            </div>
            <p>
              {selected?.label ??
                "Choose or create a saved context in Profiles."}
            </p>
            {!selected && (
              <Link to="/profiles" className="text-primary">
                Open profiles
              </Link>
            )}
            {effective && !effective.ok && <ResultMeta r={effective} />}
            {effective?.ok && records(effective.data?.setups).length === 0 && (
              <p className="mt-3 text-sm text-muted-foreground">
                No setup is owned by this context.
              </p>
            )}
            {records(effective?.data?.setups).map((item) => (
              <div
                className="mt-3 rounded-lg border border-border p-4"
                key={String(item.operation_id)}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <strong>{String(item.harness_id)}</strong>
                    <p className="text-sm text-muted-foreground">
                      {String(record(item.setup).stable_id)} ·{" "}
                      {String(record(item.setup).version)}
                    </p>
                  </div>
                  <StatusBadge state={String(item.ownership_state)} />
                  <button
                    className="btn-secondary"
                    disabled={!editable}
                    onClick={() => void remove(item)}
                  >
                    Review removal
                  </button>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  Runtime loading: {String(item.load_state)}
                </p>
              </div>
            ))}
          </section>
          {otherPending && (
            <section className="card p-5">
              <h2 className="font-semibold">
                Another state directory has a pending operation
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Recover it through its original CLI state before starting
                another setup change.
              </p>
            </section>
          )}
          <section className="card p-5" aria-label="Review setup">
            <h2 className="mb-4 text-lg font-semibold">Review a setup</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="field-label">
                Harness
                <select
                  className="input"
                  value={harness}
                  disabled={!editable}
                  onChange={(event) => setHarness(event.target.value)}
                >
                  {harnesses.map((id) => (
                    <option key={id}>{id}</option>
                  ))}
                </select>
              </label>
              <label className="field-label">
                Setup ID
                <input
                  className="input"
                  value={setup}
                  disabled={!editable}
                  onChange={(event) => setSetup(event.target.value)}
                  placeholder="setup_…"
                />
              </label>
              <label className="field-label">
                Exact version
                <input
                  className="input"
                  value={version}
                  disabled={!editable}
                  onChange={(event) => setVersion(event.target.value)}
                  placeholder="1.0"
                />
              </label>
              <label className="field-label">
                Passport digest
                <input
                  className="input"
                  value={passport}
                  disabled={!editable}
                  onChange={(event) => setPassport(event.target.value)}
                  placeholder="sha256:…"
                />
              </label>
              <label className="field-label">
                Global configuration folder
                <input
                  className="input"
                  value={globalRoot}
                  disabled={!editable}
                  onChange={(event) => setGlobalRoot(event.target.value)}
                  placeholder="Explicit existing folder"
                />
              </label>
              <label className="field-label">
                User skill folder
                <input
                  className="input"
                  value={userRoot}
                  disabled={!editable}
                  onChange={(event) => setUserRoot(event.target.value)}
                  placeholder="Optional explicit folder"
                />
              </label>
              <label className="field-label">
                Project folder
                <input
                  className="input"
                  value={projectRoot}
                  disabled={!editable}
                  onChange={(event) => setProjectRoot(event.target.value)}
                  placeholder="Optional explicit checkout"
                />
              </label>
              {selected?.mode === "corporate" && (
                <label className="field-label">
                  Company project binding
                  <input
                    className="input"
                    value={binding}
                    disabled={!editable}
                    onChange={(event) => setBinding(event.target.value)}
                    placeholder="Original linked operation ID"
                  />
                </label>
              )}
            </div>
            <div className="mt-4 space-y-3 text-sm">
              <label className="flex gap-2">
                <input
                  type="checkbox"
                  checked={replace}
                  disabled={!editable}
                  onChange={(event) => setReplace(event.target.checked)}
                />
                Replace the effective setup in these same folders
              </label>
              <label className="flex gap-2">
                <input
                  type="checkbox"
                  checked={trust}
                  disabled={!editable}
                  onChange={(event) => setTrust(event.target.checked)}
                />
                Trust this exact setup and its components after review
              </label>
            </div>
            <button
              className="btn-primary mt-4"
              disabled={
                !editable ||
                !selected ||
                !setup ||
                !version ||
                !passport ||
                !(globalRoot || userRoot || projectRoot)
              }
              onClick={() => void review()}
            >
              Review setup
            </button>
          </section>
          {operation && (
            <section
              className="card p-5"
              aria-label="Original configuration operation"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-lg font-semibold">Original operation</h2>
                <StatusBadge state={operation.phase} />
              </div>
              <p className="mt-3">
                {operation.label} · {operation.harness}
              </p>
              {contextChanged && (
                <p className="mt-2 text-sm text-muted-foreground">
                  The current view changed. This operation keeps its original
                  context shown above.
                </p>
              )}
              <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
                {operation.operation}
                <br />
                {operation.digest}
              </p>
              {operation.plan && (
                <Details
                  label="Reviewed file effects"
                  value={{
                    publications: operation.plan.publications,
                    handoff: operation.plan.activation,
                  }}
                />
              )}
              {operation.phase === "review" && (
                <>
                  <label className="mt-4 flex gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={confirmed}
                      onChange={(event) => setConfirmed(event.target.checked)}
                      disabled={busy}
                    />
                    I reviewed these exact effects and the original context.
                  </label>
                  <button
                    className="btn-primary mt-3"
                    disabled={!confirmed || busy}
                    onClick={() => void prepare()}
                  >
                    Prepare reviewed setup
                  </button>
                </>
              )}
              {["prepared", "applying", "finishing"].includes(
                operation.phase,
              ) && (
                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    className="btn-primary"
                    disabled={busy}
                    onClick={() => void run("apply")}
                  >
                    {operation.phase === "prepared"
                      ? "Apply when sessions are stopped"
                      : "Resume original operation"}
                  </button>
                  {operation.phase === "prepared" && (
                    <button
                      className="btn-secondary"
                      disabled={busy}
                      onClick={() => void run("cancel")}
                    >
                      Cancel preparation
                    </button>
                  )}
                </div>
              )}
              {operation.phase === "configured" && (
                <p className="mt-4 text-sm">
                  Confirm from a new harness session using{" "}
                  <code>
                    {confirmCommand ??
                      "Use the original operation and state directory in the CLI."}
                  </code>
                  . Keep the original CLI state directory.
                </p>
              )}
              {operation.phase !== "review" && (
                <button
                  className="btn-secondary mt-4"
                  disabled={busy}
                  onClick={() => void run("status")}
                >
                  Read original status
                </button>
              )}
            </section>
          )}
          {busy && <Spinner label="Checking the original native operation" />}
          {result && <ResultMeta r={result} />}
        </>
      )}
    </div>
  );
}
