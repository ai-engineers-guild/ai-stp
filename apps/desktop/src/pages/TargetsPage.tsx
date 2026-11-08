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
import FolderField from "../components/FolderField";
import { useText } from "../i18n";

export default function TargetsPage() {
  const t = useText();
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
  const [custodyView, setCustodyView] = useState<CmdResult | null>(null);
  const [operation, setOperation] = useState<NativeOperation | null>(null),
    [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false);
  const [otherPending, setOtherPending] = useState(false);
  const epoch = useRef(0),
    alive = useRef(true);
  const operationRef = useRef(operation);
  operationRef.current = operation;
  useEffect(() => {
    if (!operation) return;
    const panel = document.getElementById("native-operation");
    panel?.scrollIntoView?.({ block: "start" });
    panel?.focus({ preventScroll: true });
  }, [operation?.operation, operation?.phase]);
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
          restartRequired:
            typeof response.data?.restart_required === "boolean"
              ? response.data.restart_required
              : typeof record(response.data?.receipt).restart_required ===
                  "boolean"
                ? (record(response.data?.receipt).restart_required as boolean)
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
      if (alive.current) {
        setResult(response);
        setOperation(nativeStatus(response));
      }
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function reviewExisting(
    item: Record<string, unknown>,
    action: "remove" | "retire",
  ) {
    if (!editable) return;
    const values = {
      operation: String(item.operation_id ?? ""),
      "plan-digest": String(item.plan_digest ?? ""),
    };
    setBusy(true);
    setConfirmed(false);
    try {
      const response = await cliPlan(
        "configuration native " + action + " plan",
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
      const response = await cmdRunRead("configuration native custody");
      if (alive.current) setCustodyView(response);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  const contextChanged = operation && selected?.id !== operation.context;
  const confirmCommand = operation
    ? confirmationCommand(operation, String(capabilities?.data?.os ?? "linux"))
    : null;
  const publications = records(operation?.plan?.publications);
  const isGuard = (item: Record<string, unknown>) =>
    /^\.(claude|codex|cursor|grok|pi|opencode|antigravity)-setup-system\/journal\.json$/.test(
      String(item.path),
    );
  const files = publications.filter((item) => !isGuard(item));
  const guards = publications.filter(isGuard).length;
  const sessions = records(record(operation?.plan?.activation).sessions);
  const hasSetup = Boolean(setup && version && passport);
  const hasFolders = Boolean(globalRoot || userRoot || projectRoot);
  const step = operation
    ? operation.phase === "review"
      ? 2
      : 3
    : hasSetup
      ? 1
      : 0;
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("common.workspace")}
        title={t("setup.title")}
        description={t("setup.description")}
      />
      {native.available !== true ? (
        <EmptyState title={t("targets.nativeConfigurationUnavailable")}>
          {t("targets.useACliDesktopPairWithTheQualifiedNative")}
        </EmptyState>
      ) : (
        <>
          <ol className="setup-progress" aria-label={t("setup.steps")}>
            {(
              [
                "setup.stepChoose",
                "setup.stepFolders",
                "setup.stepReview",
                "setup.stepApply",
              ] as const
            ).map((key, index) => (
              <li key={key} aria-current={step === index ? "step" : undefined}>
                <span className="step-number" aria-hidden="true">
                  {index + 1}
                </span>
                <span>{t(key)}</span>
              </li>
            ))}
          </ol>
          <section
            className="card space-y-5 p-5"
            aria-label={t("targets.reviewSetup")}
          >
            <div>
              <h2 className="text-lg font-semibold">
                {t("setup.chooseTitle")}
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                {t("setup.chooseHelp")}
              </p>
              <Link to="/catalog" className="btn-outline mt-3">
                {t("setup.browse")}
              </Link>
            </div>
            {hasSetup && (
              <div className="rounded-lg border border-border bg-background p-4">
                <p className="eyebrow">{t("setup.selected")}</p>
                <p className="mt-2 font-mono text-sm break-all">
                  {setup} · {version}
                </p>
              </div>
            )}
            <label className="field-label">
              {t("setup.tool")}
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
            <details
              className="technical-details"
              open={
                !(
                  params.get("setup") &&
                  params.get("version") &&
                  params.get("digest")
                ) || undefined
              }
            >
              <summary>{t("setup.coordinates")}</summary>
              <div className="grid gap-4 md:grid-cols-2">
                <label className="field-label">
                  {t("setup.id")}
                  <input
                    className="input"
                    value={setup}
                    disabled={!editable}
                    onChange={(event) => setSetup(event.target.value)}
                    placeholder={t("targets.setup")}
                  />
                </label>
                <label className="field-label">
                  {t("setup.version")}
                  <input
                    className="input"
                    value={version}
                    disabled={!editable}
                    onChange={(event) => setVersion(event.target.value)}
                    placeholder="1.0"
                  />
                </label>
                <label className="field-label">
                  {t("setup.digest")}
                  <input
                    className="input"
                    value={passport}
                    disabled={!editable}
                    onChange={(event) => setPassport(event.target.value)}
                    placeholder={t("targets.sha256")}
                  />
                </label>
              </div>
            </details>
            <div className="space-y-4 border-t border-border pt-5">
              <div>
                <h2 className="text-lg font-semibold">
                  {t("setup.folderTitle")}
                </h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                  {t("setup.folderHelp")}
                </p>
              </div>
              <FolderField
                label={t("setup.global")}
                help={t("setup.globalHelp")}
                value={globalRoot}
                disabled={!editable}
                onChange={setGlobalRoot}
              />
              <FolderField
                label={t("setup.user")}
                help={t("setup.userHelp")}
                value={userRoot}
                disabled={!editable}
                onChange={setUserRoot}
              />
              <FolderField
                label={t("setup.project")}
                help={t("setup.projectHelp")}
                value={projectRoot}
                disabled={!editable}
                onChange={setProjectRoot}
              />
              {selected?.mode === "corporate" && (
                <label className="field-label">
                  {t("targets.companyProjectBinding")}
                  <input
                    className="input"
                    value={binding}
                    disabled={!editable}
                    onChange={(event) => setBinding(event.target.value)}
                    placeholder={t("targets.originalLinkedOperationId")}
                  />
                </label>
              )}
            </div>
            <details className="technical-details">
              <summary>{t("setup.advanced")}</summary>
              <div className="mt-4 space-y-3 text-sm">
                <label className="field-label">
                  {t("targets.change")}
                  <select
                    className="input"
                    value={changeKind}
                    disabled={!editable}
                    onChange={(event) => setChangeKind(event.target.value)}
                  >
                    <option value="install">
                      {t("targets.installInUnownedFolders")}
                    </option>
                    <option value="replace">
                      {t("targets.replaceTheEffectiveSetupInTheSameFolders")}
                    </option>
                    <option value="adopt">
                      {t("targets.adoptAnExistingExternalInstallation")}
                    </option>
                  </select>
                </label>
                {changeKind === "adopt" && (
                  <p className="text-muted-foreground">
                    {t(
                      "targets.theExistingInstallationMustBeCompleteAndMatchThis",
                    )}
                  </p>
                )}
                <label className="flex gap-2">
                  <input
                    type="checkbox"
                    checked={trust}
                    disabled={!editable}
                    onChange={(event) => setTrust(event.target.checked)}
                  />
                  {t("targets.trustThisExactSetupAndItsComponentsAfterReview")}
                </label>
              </div>
            </details>
            {!selected && (
              <p className="text-sm text-muted-foreground">
                {t("setup.contextNeeded")}{" "}
                <Link to="/profiles" className="text-primary hover:underline">
                  {t("setup.contextAction")}
                </Link>
              </p>
            )}
            <div className="space-y-3 border-t border-border pt-4">
              <p className="field-help">{t("setup.reviewHelp")}</p>
              {!hasFolders && (
                <p className="field-help">{t("setup.folderRequired")}</p>
              )}
              <button
                className="btn-primary"
                disabled={!editable || !selected || !hasSetup || !hasFolders}
                onClick={() => void review()}
              >
                {t("setup.readyReview")}
              </button>
            </div>
          </section>
          {operation && (
            <section
              className="card p-5"
              aria-label={t("targets.originalConfigurationOperation")}
              id="native-operation"
              tabIndex={-1}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-lg font-semibold">
                  {t("setup.operationTitle")}
                </h2>
                <StatusBadge state={operation.phase} />
              </div>
              <p className="mt-3 text-sm text-muted-foreground">
                {t("setup.savedHelp")}
              </p>
              <p className="mt-3">
                {operation.label} · {operation.harness}
              </p>
              {contextChanged && (
                <p className="mt-2 text-sm text-muted-foreground">
                  {t(
                    "targets.theCurrentViewChangedThisOperationKeepsItsOriginal",
                  )}
                </p>
              )}
              <details className="technical-details mt-3">
                <summary>{t("setup.operationDetails")}</summary>
                <p className="font-mono text-xs break-all text-muted-foreground">
                  {operation.operation}
                  <br />
                  {operation.digest}
                </p>
              </details>
              {operation.metadataOnly && (
                <p className="mt-3 text-sm">
                  {t(
                    "targets.thisRetiresReferencesToPositivelyMissingFoldersItChanges",
                  )}
                </p>
              )}
              {operation.plan && (
                <div className="mt-4">
                  <h3 className="font-semibold">
                    {t("targets.changesToReview")}
                  </h3>
                  {files.length === 0 ? (
                    <p className="mt-2 text-sm">
                      {t("targets.noConfigurationFileChangesAreRequired")}
                    </p>
                  ) : (
                    <div className="mt-3 overflow-x-auto">
                      <table className="w-full text-start text-sm">
                        <thead>
                          <tr className="border-b border-border">
                            <th className="py-2 pe-3">{t("targets.folder")}</th>
                            <th className="py-2 pe-3">{t("targets.file")}</th>
                            <th className="py-2">{t("targets.change")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {files.map((item, index) => {
                            const root = record(item.root),
                              path = root.path;
                            const folder =
                              typeof path === "string"
                                ? path
                                : String(
                                    record(path).display ?? "Original folder",
                                  );
                            return (
                              <tr
                                className="border-b border-border"
                                key={index}
                              >
                                <td className="py-2 pe-3 break-all">
                                  {folder}
                                </td>
                                <td className="py-2 pe-3 break-all">
                                  {String(item.path)}
                                </td>
                                <td className="py-2">
                                  {item.after == null
                                    ? t("targets.remove")
                                    : record(item.before).file == null
                                      ? t("targets.create")
                                      : t("targets.update")}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {guards > 0 && (
                    <p className="mt-3 text-sm">
                      {t(
                        "targets.historicalExternalSetupWritersWillBeBlockedInThese",
                      )}
                    </p>
                  )}
                  {sessions.length > 0 && (
                    <p className="mt-3 text-sm">
                      {t(
                        "targets.stopTheOriginalHarnessSessionsBeforeApplying",
                      )}{" "}
                      {sessions
                        .map((session) => String(session.pid))
                        .join(", ")}
                      .
                    </p>
                  )}
                </div>
              )}
              {operation.plan && (
                <Details
                  label={t("targets.exactFileFingerprintsAndHandoff")}
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
                    {t(
                      "targets.iReviewedTheseExactEffectsAndTheOriginalContext",
                    )}
                  </label>
                  <button
                    className="btn-primary mt-3"
                    disabled={!confirmed || busy}
                    onClick={() => void prepare()}
                  >
                    {t("targets.prepareReviewedSetup")}
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
                      ? t("targets.applyWhenSessionsAreStopped")
                      : t("targets.resumeOriginalOperation")}
                  </button>
                  {operation.phase === "prepared" && (
                    <button
                      className="btn-secondary"
                      disabled={busy}
                      onClick={() => void run("cancel")}
                    >
                      {t("targets.cancelPreparation")}
                    </button>
                  )}
                </div>
              )}
              {operation.phase === "configured" &&
                operation.restartRequired !== false && (
                  <p className="mt-4 text-sm">
                    {t("targets.confirmFromANewHarnessSessionUsing")}{" "}
                    <code>
                      {confirmCommand ??
                        "Use the original operation and state directory in the CLI."}
                    </code>
                    {t("targets.keepTheOriginalCliStateDirectory")}
                  </p>
                )}
              {operation.phase === "configured" &&
                operation.restartRequired === false && (
                  <p className="mt-4 text-sm">
                    {t(
                      "targets.configurationIsCurrentThisOperationDidNotRequireA",
                    )}
                  </p>
                )}
              {operation.phase === "confirmed" && (
                <p className="mt-4 text-sm">
                  {t(
                    "targets.theOriginalOperationIsConfirmedRuntimeLoadingRemainsUnobserved",
                  )}
                </p>
              )}
              {operation.phase !== "review" && (
                <button
                  className="btn-secondary mt-4"
                  disabled={busy}
                  onClick={() => void run("status")}
                >
                  {t("targets.readOriginalStatus")}
                </button>
              )}
            </section>
          )}
          <section
            className="card p-5"
            aria-label={t("targets.effectiveSetup")}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                {t("targets.currentContext")}
              </h2>
              <button
                className="btn-secondary"
                disabled={busy}
                onClick={() => void refresh()}
              >
                {t("common.refresh")}
              </button>
            </div>
            <p>
              {selected?.label ??
                t("targets.chooseOrCreateASavedContextInProfiles")}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-primary">
              <Link to="/catalog" className="inline-flex min-h-6 items-center">
                {t("targets.browseSetups")}
              </Link>
              <Link to="/install?intent=author">
                {t("targets.createFromLocalFiles")}
              </Link>
            </div>
            {!selected && (
              <Link
                to="/profiles"
                className="inline-flex min-h-6 items-center text-primary"
              >
                {t("targets.openProfiles")}
              </Link>
            )}
            {effective && !effective.ok && <ResultMeta r={effective} />}
            {effective?.ok && records(effective.data?.setups).length === 0 && (
              <p className="mt-3 text-sm text-muted-foreground">
                {t("targets.noSetupIsOwnedByThisContext")}
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
                    disabled={busy}
                    onClick={() => void inspect(item)}
                  >
                    {t("targets.inspectOriginalOperation")}
                  </button>
                  <button
                    className="btn-secondary"
                    disabled={!editable}
                    onClick={() => void reviewExisting(item, "remove")}
                  >
                    {t("targets.reviewRemoval")}
                  </button>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {t("targets.runtimeLoading")} {String(item.load_state)}
                </p>
              </div>
            ))}
          </section>
          <details
            className="card p-5"
            aria-label={t("targets.missingFolders")}
          >
            <summary className="section-title">{t("setup.recovery")}</summary>
            <p className="mt-2 text-sm text-muted-foreground">
              {t(
                "targets.inspectLocalOwnershipAcrossContextsWhenAnOriginalFolder",
              )}
            </p>
            <button
              className="btn-secondary mt-3"
              disabled={busy}
              onClick={() => void inspectCustody()}
            >
              {t("targets.findMissingFolders")}
            </button>
            {records(custodyView?.data?.operations)
              .filter((item) =>
                records(item.roots).some((root) => root.state === "missing"),
              )
              .map((item) => (
                <div
                  className="mt-3 rounded-lg border border-border p-4"
                  key={String(item.operation_id)}
                >
                  <p>
                    {String(record(item.original_context).label)} ·{" "}
                    {String(item.harness_id)}
                  </p>
                  <button
                    className="btn-secondary mt-3"
                    disabled={!editable}
                    onClick={() => void reviewExisting(item, "retire")}
                  >
                    {t("targets.reviewMissingFolderRetirement")}
                  </button>
                </div>
              ))}
            {custodyView?.ok &&
              records(custodyView.data?.operations).every((item) =>
                records(item.roots).every((root) => root.state !== "missing"),
              ) && (
                <p className="mt-3 text-sm">
                  {t("targets.noOwnedFolderWasPositivelyObservedAsMissing")}
                </p>
              )}
            {record(custodyView?.data?.pending).operation_id != null && (
              <Details
                label={t("targets.retainedOriginalRecoveryCoordinates")}
                value={custodyView?.data?.pending}
              />
            )}
            {custodyView && !custodyView.ok && <ResultMeta r={custodyView} />}
          </details>
          {otherPending && (
            <section className="card p-5">
              <h2 className="font-semibold">
                {t("targets.anotherStateDirectoryHasAPendingOperation")}
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">
                {t("targets.recoverItThroughItsOriginalCliStateBeforeStarting")}
              </p>
            </section>
          )}
          {selected?.mode === "corporate" &&
            record(capabilities?.data?.native_inventory).available === true && (
              <NativeInventory context={selected} />
            )}
          {busy && <Spinner label={t("setup.loading")} />}
          {result && <ResultMeta r={result} />}
        </>
      )}
    </div>
  );
}
