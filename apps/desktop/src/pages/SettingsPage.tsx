import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ArrowRight, KeyRound } from "lucide-react";
import { useApp, useDebug } from "../store";
import {
  cliApplyConfirmed,
  cmdMachineHelp,
  descriptorChoices,
  type CmdResult,
} from "../transport";
import { PageHeader, StatusBadge } from "../components/Layout";
import { ResultMeta } from "../components/Result";

export default function SettingsPage() {
  const { location, doctor, capabilities, refreshCli, refreshAuth } = useApp();
  const { debugMode, setDebugMode } = useDebug();
  const [stores, setStores] = useState<string[]>([]);
  const [store, setStore] = useState("os_keyring");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CmdResult | null>(null);
  const [help, setHelp] = useState<CmdResult | null>(null);
  useEffect(() => {
    let current = true;
    void cmdMachineHelp().then((result) => {
      if (!current) return;
      setHelp(result);
      setStores(descriptorChoices(result, "init", "credential-store") ?? []);
    });
    return () => {
      current = false;
    };
  }, []);
  const ready = (
    doctor?.data?.checks as { name: string; state: string }[] | undefined
  )?.some(
    (check) => check.name === "local_identity" && check.state === "ready",
  );
  const choices = stores.filter(
    (choice) => choice !== "file" || capabilities?.data?.os !== "windows",
  );
  async function initialize() {
    if (!confirmed || busy) return;
    setBusy(true);
    try {
      const response = await cliApplyConfirmed(
        "init",
        { "credential-store": store },
        [],
        true,
      );
      setResult(response);
      setConfirmed(false);
      await refreshCli();
      await refreshAuth();
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="System"
        title="Settings"
        description="Your local workspace, credentials and application preferences."
      />
      <section className="card space-y-5 p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="section-title">Local workspace</h2>
            <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
              {String(location?.data?.state_dir ?? "Resolving location…")}
            </p>
          </div>
          <StatusBadge state={ready ? "ready" : "needs_user_action"}>
            {ready ? "Initialized" : "Setup needed"}
          </StatusBadge>
        </div>
        <p className="text-sm leading-6 text-muted-foreground">
          The app and CLI share one local identity and operation history.
          Opening the app does not initialize or migrate your data.
        </p>
        {!ready && (
          <form
            className="space-y-4 border-t border-border pt-5"
            onSubmit={(event) => {
              event.preventDefault();
              void initialize();
            }}
          >
            <label className="field-label max-w-sm">
              <span className="flex items-center gap-2">
                <KeyRound size={15} />
                Credential storage
              </span>
              <select
                className="input"
                value={store}
                disabled={busy}
                onChange={(event) => {
                  setStore(event.target.value);
                  setConfirmed(false);
                }}
              >
                {choices.map((choice) => (
                  <option key={choice} value={choice}>
                    {choice === "os_keyring"
                      ? "Operating system keyring"
                      : choice === "file"
                        ? "Local file (unencrypted)"
                        : choice}
                  </option>
                ))}
              </select>
            </label>
            <p className="text-xs leading-5 text-muted-foreground">
              {store === "file"
                ? "File storage is unencrypted and available only on Unix. The CLI restricts access to the owner."
                : "Uses the operating system credential service. The CLI never silently falls back to file storage."}
            </p>
            <label className="flex items-start gap-3 text-sm">
              <input
                className="mt-1"
                type="checkbox"
                checked={confirmed}
                disabled={busy}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              Initialize or resume this device using the selected credential
              storage.
            </label>
            <button
              className="btn-primary"
              disabled={busy || !confirmed || !choices.includes(store)}
            >
              {busy ? "Initializing…" : "Initialize workspace"}
              <ArrowRight size={14} />
            </button>
          </form>
        )}
        {help && !help.ok && <ResultMeta r={help} />}
        {result && <ResultMeta r={result} />}
      </section>
      <section className="card space-y-4 p-6">
        <h2 className="section-title">Advanced state operations</h2>
        <p className="text-sm leading-6 text-muted-foreground">
          An existing Python workspace requires an explicit migration plan and
          its exact digest. Inspect configuration or migration status through
          the native command forms.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            className="btn-outline"
            to="/registry?command=state%20migrate%20plan"
          >
            Migration plan
          </Link>
          <Link
            className="btn-outline"
            to="/registry?command=state%20migrate%20status"
          >
            Migration status
          </Link>
          <Link className="btn-outline" to="/registry?command=config%20show">
            View configuration
          </Link>
        </div>
      </section>
      <section className="card space-y-3 p-6">
        <h2 className="section-title">Local diagnostics</h2>
        <label className="flex items-center gap-3 text-sm">
          <input
            type="checkbox"
            checked={debugMode}
            onChange={(event) => setDebugMode(event.target.checked)}
          />
          Record a temporary IPC trace
        </label>
        <p className="text-xs leading-5 text-muted-foreground">
          Kept in memory on this device. Nothing is sent automatically. Review
          and copy a redacted report in Diagnostics.
        </p>
      </section>
    </div>
  );
}
