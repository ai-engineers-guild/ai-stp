import { iconSize } from "../generated/theme";
import { formatTime, useText } from "../i18n";
import { useEffect, useState } from "react";
import { ClipboardCopy, Play, Trash2 } from "lucide-react";
import { cmdDebugInfo, cmdRunRead, type CmdResult } from "../transport";
import { Json, ResultMeta } from "../components/Result";
import { PageHeader } from "../components/Layout";
import { useDebug } from "../store";

/** Debug surface: every IPC call with latency and outcome, the resolved
 *  CLI binary, and a raw-envelope inspector. Nothing here writes — the
 *  inspector is gated to mutability=read on the shell side anyway. */
export default function DebugPage() {
  const msg = useText();
  const { log, clear, debugMode, setDebugMode } = useDebug();
  const [info, setInfo] = useState<CmdResult | null>(null);
  const [probe, setProbe] = useState("version");
  const [probeResult, setProbeResult] = useState<CmdResult | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);

  useEffect(() => {
    void (async () => setInfo(await cmdDebugInfo()))();
  }, []);

  async function runProbe() {
    setProbeResult(await cmdRunRead(probe));
  }

  async function copyBundle() {
    // The shared report has its own allowlist. Local inspection may contain
    // paths and command content, including fields added by future commands.
    const bundle = {
      generated_at: new Date().toISOString(),
      environment: info?.data
        ? {
            app_version: info.data.app_version,
            platform: info.data.platform,
            arch: info.data.arch,
            cli_found: info.data.cli_found,
            cli_source: info.data.cli_source,
          }
        : null,
      ipc_log: log.slice(0, 50).map(({ ts, cmd, ms, ok, error_code }) => ({
        ts,
        cmd,
        ms,
        ok,
        error_code,
      })),
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(bundle, null, 2));
      setCopied(true);
      setCopyError(false);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // No clipboard permission in the webview — offer nothing false.
      setCopyError(true);
      setTimeout(() => setCopyError(false), 2500);
    }
  }

  const failures = log.filter((e) => e.ok === false || e.ok === null);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={msg("debug.system")}
        title={msg("shell.diagnostics")}
        description={msg(
          "debug.localEngineInformationAndAnOptionalTraceForTroubleshooting",
        )}
        action={
          <div className="flex gap-2">
            <button onClick={() => void copyBundle()} className="btn-outline">
              <ClipboardCopy style={iconSize.sm} />
              {copied
                ? msg("debug.copied")
                : copyError
                  ? msg("debug.clipboardUnavailable")
                  : msg("debug.copyReport")}
            </button>
            <button onClick={clear} className="btn-outline">
              <Trash2 style={iconSize.sm} />
              {msg("debug.clear")}
            </button>
          </div>
        }
      />
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={debugMode}
          onChange={(event) => setDebugMode(event.target.checked)}
        />
        {msg("debug.recordATemporaryLocalTrace")}
      </label>

      <section className="card p-4">
        <h2 className="section-title mb-2">{msg("debug.environment")}</h2>
        {info?.data ? (
          <Json v={info.data} />
        ) : (
          <p className="text-sm text-muted-foreground">…</p>
        )}
      </section>

      <section className="card space-y-2 p-4">
        <h2 className="section-title">{msg("debug.envelopeInspector")}</h2>
        <p className="text-xs text-muted-foreground">
          {msg("debug.runsAReadTierCommandAndShowsTheRaw")}
        </p>
        <div className="flex gap-2">
          <input
            value={probe}
            onChange={(e) => setProbe(e.target.value)}
            aria-label={msg("debug.readOnlyCommand")}
            placeholder={msg("debug.commandPathEGVersion")}
            className="input w-72 font-mono"
          />
          <button onClick={() => void runProbe()} className="btn-primary">
            <Play style={iconSize.sm} /> {msg("debug.run")}
          </button>
        </div>
        {probeResult && (
          <>
            <ResultMeta r={probeResult} />
            <Json v={probeResult} />
          </>
        )}
      </section>

      <section className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-border px-4 py-2">
          <h2 className="section-title">
            {msg("debug.ipcTrace", { count: log.length })}
          </h2>
          <p className="text-xs text-muted-foreground">
            {msg("debug.failureS", { count: failures.length })}
          </p>
        </div>
        <ul className="max-h-96 divide-y divide-border overflow-auto font-mono text-xs">
          {log.length === 0 && (
            <li className="px-4 py-3 text-muted-foreground">
              {debugMode
                ? msg("debug.noCallsYet")
                : msg("debug.ipcTraceIsOffEnableItAbove")}
            </li>
          )}
          {log.map((e) => (
            <li key={e.id}>
              <button
                onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                aria-expanded={expanded === e.id}
                className="flex w-full items-center gap-3 px-4 py-1.5 text-start hover:bg-accent"
              >
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                    e.ok === null
                      ? "bg-warning"
                      : e.ok
                        ? "bg-success"
                        : "bg-destructive"
                  }`}
                />
                <span className="w-40 shrink-0">{e.cmd}</span>
                <span className="min-w-16 shrink-0 text-muted-foreground">
                  {msg("debug.ms", { duration: e.ms })}
                </span>
                <span className="flex-1 truncate text-muted-foreground">
                  {e.error_code ?? (e.ok ? msg("debug.ok") : "—")}
                </span>
                <span className="shrink-0 text-muted-foreground">
                  {formatTime(e.ts)}
                </span>
              </button>
              {expanded === e.id && (
                <div className="border-t border-border bg-muted/40 px-4 py-2">
                  <p className="mb-1 text-muted-foreground">
                    {msg("debug.args")} {JSON.stringify(e.args)}
                  </p>
                  {e.result && <Json v={e.result} />}
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
