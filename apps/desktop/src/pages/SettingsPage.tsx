import { iconSize } from "../generated/theme";
import { useText } from "../i18n";
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
import LanguageSelect from "../components/LanguageSelect";

export default function SettingsPage() {
  const msg = useText();
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
        eyebrow={msg("settings.system")}
        title={msg("shell.settings")}
        description={msg(
          "settings.yourLocalWorkspaceCredentialsAndApplicationPreferences",
        )}
      />
      <section className="card space-y-5 p-6">
        <LanguageSelect />
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="section-title">{msg("settings.localWorkspace")}</h2>
            <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
              {String(
                location?.data?.state_dir ?? msg("settings.resolvingLocation"),
              )}
            </p>
          </div>
          <StatusBadge state={ready ? "ready" : "needs_user_action"}>
            {ready ? msg("settings.initialized") : msg("settings.setupNeeded")}
          </StatusBadge>
        </div>
        <p className="text-sm leading-6 text-muted-foreground">
          {msg("settings.theAppAndCliShareOneLocalIdentityAnd")}
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
                <KeyRound style={iconSize.sm} />
                {msg("settings.credentialStorage")}
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
                      ? msg("settings.operatingSystemKeyring")
                      : choice === "file"
                        ? msg("settings.localFileUnencrypted")
                        : choice}
                  </option>
                ))}
              </select>
            </label>
            <p className="text-xs leading-5 text-muted-foreground">
              {store === "file"
                ? msg("settings.fileStorageIsUnencryptedAndAvailableOnlyOnUnix")
                : msg(
                    "settings.usesTheOperatingSystemCredentialServiceTheCliNever",
                  )}
            </p>
            <label className="flex items-start gap-3 text-sm">
              <input
                className="mt-1"
                type="checkbox"
                checked={confirmed}
                disabled={busy}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              {msg(
                "settings.initializeOrResumeThisDeviceUsingTheSelectedCredential",
              )}
            </label>
            <button
              className="btn-primary"
              disabled={busy || !confirmed || !choices.includes(store)}
            >
              {busy
                ? msg("settings.initializing")
                : msg("settings.initializeWorkspace")}
              <ArrowRight style={iconSize.sm} />
            </button>
          </form>
        )}
        {help && !help.ok && <ResultMeta r={help} />}
        {result && <ResultMeta r={result} />}
      </section>
      <section className="card space-y-4 p-6">
        <h2 className="section-title">
          {msg("settings.advancedStateOperations")}
        </h2>
        <p className="text-sm leading-6 text-muted-foreground">
          {msg(
            "settings.anExistingPythonWorkspaceRequiresAnExplicitMigrationPlan",
          )}
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            className="btn-outline"
            to="/registry?command=state%20migrate%20plan"
          >
            {msg("settings.migrationPlan")}
          </Link>
          <Link
            className="btn-outline"
            to="/registry?command=state%20migrate%20status"
          >
            {msg("settings.migrationStatus")}
          </Link>
          <Link className="btn-outline" to="/registry?command=config%20show">
            {msg("settings.viewConfiguration")}
          </Link>
        </div>
      </section>
      <section className="card space-y-3 p-6">
        <h2 className="section-title">{msg("settings.localDiagnostics")}</h2>
        <label className="flex items-center gap-3 text-sm">
          <input
            type="checkbox"
            checked={debugMode}
            onChange={(event) => setDebugMode(event.target.checked)}
          />
          {msg("settings.recordATemporaryIpcTrace")}
        </label>
        <p className="text-xs leading-5 text-muted-foreground">
          {msg("settings.keptInMemoryOnThisDeviceNothingIsSent")}
        </p>
      </section>
    </div>
  );
}
