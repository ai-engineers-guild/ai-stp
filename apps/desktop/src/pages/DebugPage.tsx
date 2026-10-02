import { useEffect, useState } from "react";
import { Bug, ClipboardCopy, Play, Trash2 } from "lucide-react";
import { cmdDebugInfo, cmdRunRead, type CmdResult } from "../transport";
import { Json, ResultMeta } from "../components/Result";
import { useDebug } from "../store";

/** Debug surface: every IPC call with latency and outcome, the resolved
 *  CLI binary, and a raw-envelope inspector. Nothing here writes — the
 *  inspector is gated to mutability=read on the shell side anyway. */
export default function DebugPage() {
  const { log, clear, debugMode } = useDebug();
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
    const bundle = {
      generated_at: new Date().toISOString(),
      environment: info?.data,
      ipc_log: log.slice(0, 50),
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
    <div className="space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Bug size={18} /> Debug
          </h1>
          <p className="page-sub">IPC trace, resolved engine, envelope inspector.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => void copyBundle()} className="btn-outline">
            <ClipboardCopy size={14} />{" "}
            {copied ? "Copied" : copyError ? "Clipboard unavailable" : "Diagnostic bundle"}
          </button>
          <button onClick={clear} className="btn-outline">
            <Trash2 size={14} /> Clear
          </button>
        </div>
      </header>

      <section className="card p-4">
        <h2 className="section-title mb-2">Environment</h2>
        {info?.data ? <Json v={info.data} /> : <p className="text-sm text-muted-foreground">…</p>}
      </section>

      <section className="card space-y-2 p-4">
        <h2 className="section-title">Envelope inspector</h2>
        <p className="text-xs text-muted-foreground">
          Runs a read-tier command and shows the raw envelope — continuations, warnings, error codes.
        </p>
        <div className="flex gap-2">
          <input value={probe} onChange={(e) => setProbe(e.target.value)}
            placeholder="command path, e.g. `harness status`"
            className="input w-72 font-mono" />
          <button onClick={() => void runProbe()} className="btn-primary">
            <Play size={14} /> Run
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
          <h2 className="section-title">IPC trace ({log.length})</h2>
          <p className="text-xs text-muted-foreground">{failures.length} failure(s)</p>
        </div>
        <ul className="max-h-96 divide-y divide-border overflow-auto font-mono text-xs">
          {log.length === 0 && (
            <li className="px-4 py-3 text-muted-foreground">
              {debugMode
                ? "No calls yet."
                : "IPC trace is off — enable \"debug trace\" in the sidebar."}
            </li>
          )}
          {log.map((e) => (
            <li key={e.id}>
              <button
                onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                className="flex w-full items-center gap-3 px-4 py-1.5 text-left hover:bg-accent"
              >
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                    e.ok === null ? "bg-warning" : e.ok ? "bg-success" : "bg-destructive"
                  }`}
                />
                <span className="w-40 shrink-0">{e.cmd}</span>
                <span className="w-16 shrink-0 text-muted-foreground">{e.ms}ms</span>
                <span className="flex-1 truncate text-muted-foreground">
                  {e.error_code ?? (e.ok ? "ok" : "—")}
                </span>
                <span className="shrink-0 text-muted-foreground">
                  {new Date(e.ts).toLocaleTimeString()}
                </span>
              </button>
              {expanded === e.id && (
                <div className="border-t border-border bg-muted/40 px-4 py-2">
                  <p className="mb-1 text-muted-foreground">args: {JSON.stringify(e.args)}</p>
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
