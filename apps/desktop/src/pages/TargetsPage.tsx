import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
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
  nativeStatus,
  type NativeOperation,
} from "../nativeConfiguration";
import { Details, ResultMeta, Spinner } from "../components/Result";
import { EmptyState, PageHeader, StatusBadge } from "../components/Layout";
import NativeInventory from "../components/NativeInventory";

export default function TargetsPage() {
  const [params] = useSearchParams();
  const { selected, refresh: refreshContexts } = useContexts();
  const capabilities = useApp((state) => state.capabilities);
  const native = record(capabilities?.data?.native_configuration);
  const harnesses = Array.isArray(native.harnesses)
    ? native.harnesses.filter(
        (value): value is string => typeof value === "string",
      )
    : [];
  const [harness, setHarness] = useState(params.get("harness") || "codex"),
    [setup, setSetup] = useState(params.get("setup") ?? "");
  const [version, setVersion] = useState(params.get("version") ?? ""),
    [passport, setPassport] = useState(params.get("digest") ?? "");
  const [globalRoot, setGlobalRoot] = useState(""),
    [userRoot, setUserRoot] = useState(""),
    [projectRoot, setProjectRoot] = useState("");
  const [binding, setBinding] = useState(""),
    [changeKind, setChangeKind] = useState("install"),
    [trust, setTrust] = useState(false);
  const [result, setResult] = useState<CmdResult | null>(null),
    [effective, setEffective] = useState<CmdResult | null>(null);
  const [custodyView,setCustodyView] = useState<CmdResult | null>(null);
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
        operation: changeKind,
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
      if (response.ok)
        setOperation({
          ...held,
          phase:
            typeof response.data?.state === "string"
              ? response.data.state
              : "prepared",
        });
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
          restartRequired: typeof response.data?.restart_required === "boolean"
            ? response.data.restart_required
            : typeof record(response.data?.receipt).restart_required === "boolean"
              ? record(response.data?.receipt).restart_required as boolean
              : held.restartRequired,
          phase:
            action === "apply"
              ? String(response.data?.state ?? "configured")
              : action === "cancel"
                ? "cancelled"
                : String(response.data?.state ?? held.phase),
        });
      if (response.ok && action === "apply") setCustodyView(null);
      await refresh();
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function inspect(item: Record<string, unknown>) {
    if (busy) return;
    setBusy(true);
    try {
      const response = await cmdRunRead("configuration native status", {
        operation: String(item.operation_id ?? ""),
        "plan-digest": String(item.plan_digest ?? ""),
      });
      if (alive.current) { setResult(response); setOperation(nativeStatus(response)); }
    } finally { if (alive.current) setBusy(false); }
  }
  async function reviewExisting(item: Record<string, unknown>, action: "remove" | "retire") {
    if (!editable) return;
    const values = {
      operation: String(item.operation_id ?? ""),
      "plan-digest": String(item.plan_digest ?? ""),
    };
    setBusy(true);
    setConfirmed(false);
    try {
      const response = await cliPlan(
        "configuration native "+action+" plan",
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
  async function inspectCustody() {
    if (busy) return;
    setBusy(true);
    try {
      const response=await cmdRunRead("configuration native custody");
      if (alive.current) setCustodyView(response);
    } finally { if (alive.current) setBusy(false); }
  }
  const contextChanged = operation && selected?.id !== operation.context;
  const confirmCommand = operation
    ? confirmationCommand(operation, String(capabilities?.data?.os ?? "linux"))
    : null;
  const publications = records(operation?.plan?.publications);
  const isGuard = (item: Record<string, unknown>) => /^\.(claude|codex|cursor|grok|pi|opencode|antigravity)-setup-system\/journal\.json$/.test(String(item.path));
  const files = publications.filter(item => !isGuard(item));
  const guards = publications.filter(isGuard).length;
  const sessions = records(record(operation?.plan?.activation).sessions);
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Workspace"
        title="Setups"
        description="Apply a reviewed setup, recover changes, and check the configuration you own."
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
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-primary">
              <Link to="/catalog" className="inline-flex min-h-6 items-center">
                Browse setups
              </Link>
              <Link to="/install?intent=author">Create from local files</Link>
            </div>
            {!selected && (
              <Link to="/profiles" className="inline-flex min-h-6 items-center text-primary">
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
                  <button className="btn-secondary" disabled={busy} onClick={() => void inspect(item)}>Inspect original operation</button>
                  <button
                    className="btn-secondary"
                    disabled={!editable}
                    onClick={() => void reviewExisting(item,"remove")}
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
          <section className="card p-5" aria-label="Missing folders">
            <h2 className="font-semibold">Missing configuration folders</h2>
            <p className="mt-2 text-sm text-muted-foreground">Inspect local ownership across contexts when an original folder or state directory was removed. Retirement releases only references to folders proved absent.</p>
            <button className="btn-secondary mt-3" disabled={busy} onClick={() => void inspectCustody()}>Find missing folders</button>
            {records(custodyView?.data?.operations).filter(item => records(item.roots).some(root => root.state === "missing")).map(item =>
              <div className="mt-3 rounded-lg border border-border p-4" key={String(item.operation_id)}>
                <p>{String(record(item.original_context).label)} · {String(item.harness_id)}</p>
                <button className="btn-secondary mt-3" disabled={!editable} onClick={() => void reviewExisting(item,"retire")}>Review missing-folder retirement</button>
              </div>)}
            {custodyView?.ok && records(custodyView.data?.operations).every(item => records(item.roots).every(root => root.state !== "missing")) && <p className="mt-3 text-sm">No owned folder was positively observed as missing.</p>}
            {record(custodyView?.data?.pending).operation_id != null && <Details label="Retained original recovery coordinates" value={custodyView?.data?.pending}/>}
            {custodyView && !custodyView.ok && <ResultMeta r={custodyView}/>}
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
            <p className="mb-4 text-sm text-muted-foreground">Choose an exact setup already available in your local library. Browse the catalog or create one from your files to obtain its version.</p>
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
              <label className="field-label">
                Change
                <select className="input" value={changeKind} disabled={!editable}
                  onChange={(event) => setChangeKind(event.target.value)}>
                  <option value="install">Install in unowned folders</option>
                  <option value="replace">Replace the effective setup in the same folders</option>
                  <option value="adopt">Adopt an existing external installation</option>
                </select>
              </label>
              {changeKind === "adopt" && <p className="text-muted-foreground">The existing installation must be complete and match this exact setup. Its original receipts and files are preserved.</p>}
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
              {operation.metadataOnly && <p className="mt-3 text-sm">This retires references to positively missing folders. It changes no configuration files and grants no installation or account access.</p>}
              {operation.plan && <div className="mt-4">
                <h3 className="font-semibold">Changes to review</h3>
                {files.length === 0 ? <p className="mt-2 text-sm">No configuration file changes are required.</p> :
                  <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm">
                    <thead><tr className="border-b border-border"><th className="py-2 pr-3">Folder</th><th className="py-2 pr-3">File</th><th className="py-2">Change</th></tr></thead>
                    <tbody>{files.map((item,index) => {
                      const root = record(item.root), path = root.path;
                      const folder = typeof path === "string" ? path : String(record(path).display ?? "Original folder");
                      return <tr className="border-b border-border" key={index}>
                        <td className="py-2 pr-3 break-all">{folder}</td><td className="py-2 pr-3 break-all">{String(item.path)}</td>
                        <td className="py-2">{item.after == null ? "Remove" : record(item.before).file == null ? "Create" : "Update"}</td>
                      </tr>;
                    })}</tbody>
                  </table></div>}
                {guards > 0 && <p className="mt-3 text-sm">Historical external setup writers will be blocked in these folders. Their original records are preserved.</p>}
                {sessions.length > 0 && <p className="mt-3 text-sm">Stop the original harness sessions before applying: {sessions.map(session => String(session.pid)).join(", ")}.</p>}
              </div>}
              {operation.plan && (
                <Details
                  label="Exact file fingerprints and handoff"
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
              {operation.phase === "configured" && operation.restartRequired !== false && (
                <p className="mt-4 text-sm">
                  Confirm from a new harness session using{" "}
                  <code>
                    {confirmCommand ??
                      "Use the original operation and state directory in the CLI."}
                  </code>
                  . Keep the original CLI state directory.
                </p>
              )}
              {operation.phase === "configured" && operation.restartRequired === false && (
                <p className="mt-4 text-sm">Configuration is current. This operation did not require a restart.</p>
              )}
              {operation.phase === "confirmed" && <p className="mt-4 text-sm">The original operation is confirmed. Runtime loading remains unobserved.</p>}
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
          {selected?.mode === "corporate" && record(capabilities?.data?.native_inventory).available === true && <NativeInventory context={selected} />}
          {busy && <Spinner label="Checking the original native operation" />}
          {result && <ResultMeta r={result} />}
        </>
      )}
    </div>
  );
}
