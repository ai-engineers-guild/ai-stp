import { useState } from "react";
import { HardDrive, RefreshCw, Wrench } from "lucide-react";
import { cliApplyConfirmed, cmdRunRead, type CmdResult } from "../transport";
import { Json, ResultMeta, Spinner } from "../components/Result";

const HARNESSES = ["antigravity", "claude-code", "codex", "cursor", "grok-build", "opencode", "pi"];

const QUERIES: { label: string; path: string; needs: ("project" | "harness")[] }[] = [
  { label: "Target status", path: "target status", needs: ["project", "harness"] },
  { label: "Backups", path: "target backups", needs: ["project", "harness"] },
  { label: "Diff vs installed", path: "target diff", needs: ["project", "harness"] },
  { label: "Rollback preview", path: "target rollback", needs: ["project", "harness"] },
  { label: "Select session", path: "select session", needs: ["harness"] },
  { label: "Select eligibility", path: "select eligibility", needs: ["harness"] },
  { label: "Stopped operations", path: "install status", needs: [] },
  { label: "Update status", path: "update status", needs: [] },
];

/** Per-target state: installed footprint, backups, drift, recovery handles.
 *  All reads through the gated `cli_run_read` path — writes stay in flows. */
export default function TargetsPage() {
  const [project, setProject] = useState("");
  const [harness, setHarness] = useState("claude-code");
  const [results, setResults] = useState<Record<string, CmdResult>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [txId, setTxId] = useState("");
  const [txTxn, setTxTxn] = useState("");
  const [txResult, setTxResult] = useState<CmdResult | null>(null);
  const [txConfirm, setTxConfirm] = useState<"resume" | "tx" | false>(false);

  async function run(q: (typeof QUERIES)[number]) {
    setBusy(q.path);
    try {
      const values: Record<string, string> = {};
      for (const n of q.needs) values[n] = n === "project" ? project : harness;
      const r = await cmdRunRead(q.path, values);
      setResults((prev) => ({ ...prev, [q.path]: r }));
    } finally {
      setBusy(null);
    }
  }

  /** `install status` reports stopped operations as RecoveryView objects
   *  keyed by `operation_id` (cli-installation-status schema). Inspection
   *  runs `install recover --operation` (read-tier); finishing the result
   *  check runs `install resume --operation` (apply-tier). */
  const stopped: string[] = (() => {
    const s = (results["install status"]?.data?.stopped ?? []) as unknown[];
    return s
      .map((e) =>
        typeof e === "string"
          ? e
          : ((e as Record<string, unknown>)?.operation_id ??
              (e as Record<string, unknown>)?.id) as string | undefined,
      )
      .filter((x): x is string => typeof x === "string" && x.length > 0);
  })();

  async function opInspect(id: string) {
    setBusy("tx");
    setTxResult(await cmdRunRead("install recover", { operation: id }));
    setBusy(null);
  }

  async function opResume(id: string) {
    setBusy("tx");
    setTxResult(
      await cliApplyConfirmed("install resume", { operation: id }, [], true),
    );
    setTxConfirm(false);
    setBusy(null);
    // Recovery changes the stopped list — refresh it if it was loaded.
    if (results["install status"]) {
      const r = await cmdRunRead("install status");
      setResults((prev) => ({ ...prev, "install status": r }));
    }
  }

  async function txInspect(id: string) {
    setBusy("tx");
    setTxResult(await cmdRunRead("install transaction status", { transaction: id }));
    setBusy(null);
  }

  async function txRecover(id: string) {
    setBusy("tx");
    setTxResult(
      await cliApplyConfirmed("install transaction recover", { transaction: id }, [], true),
    );
    setTxConfirm(false);
    setBusy(null);
    if (results["install status"]) {
      const r = await cmdRunRead("install status");
      setResults((prev) => ({ ...prev, "install status": r }));
    }
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="page-title">Targets</h1>
        <p className="text-sm text-muted-foreground">
          Installed state, backups and drift per project×harness. Read-only;
          changes go through Install.
        </p>
      </header>

      <div className="flex max-w-2xl gap-3">
        <label className="flex-1 text-xs">
          Project
          <input value={project} onChange={(e) => setProject(e.target.value)}
            placeholder="project passport id or /absolute/path"
            className="mt-1 w-full rounded-lg border border-input bg-transparent px-3 py-1.5 font-mono text-sm" />
        </label>
        <label className="w-44 text-xs">
          Harness
          <select value={harness} onChange={(e) => setHarness(e.target.value)}
            className="mt-1 w-full rounded-lg border border-input bg-transparent px-2 py-1.5 text-sm">
            {HARNESSES.map((h) => <option key={h}>{h}</option>)}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap gap-2">
        {QUERIES.map((q) => (
          <button key={q.path}
            onClick={() => void run(q)}
            disabled={(q.needs.includes("project") && !project) || busy !== null}
            className="flex items-center gap-1.5 rounded-lg border border-input px-3 py-1.5 text-sm hover:bg-accent disabled:text-muted-foreground dark:hover:bg-accent">
            {busy === q.path ? <RefreshCw size={12} className="animate-spin" /> : <HardDrive size={12} />}
            {q.label}
          </button>
        ))}
      </div>

      {stopped.length > 0 && (
        <section className="card space-y-2 p-4">
          <h2 className="section-title">Stopped operations</h2>
          <ul className="space-y-1.5">
            {stopped.map((id) => (
              <li key={id} className="flex items-center gap-2 font-mono text-xs">
                <span className="flex-1 truncate">{id}</span>
                <button onClick={() => { setTxId(id); void opInspect(id); }}
                  className="btn-outline !py-0.5 !text-[11px]">inspect</button>
                <button onClick={() => { setTxId(id); setTxConfirm("resume"); }}
                  className="btn-danger !py-0.5 !text-[11px]">resume</button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card space-y-2 p-4">
        <h2 className="section-title">Operation recovery</h2>
        <p className="text-xs text-muted-foreground">
          A stopped operation can be inspected (`install recover`) and its
          result check finished (`install resume`, apply-tier — confirm
          explicitly). For a multi-root transaction id use the second row.
        </p>
        <div className="flex gap-2">
          <input value={txId} onChange={(e) => { setTxId(e.target.value); setTxConfirm(false); }}
            placeholder="operation id, e.g. from Stopped operations above"
            className="input w-80 font-mono" />
          <button onClick={() => void opInspect(txId)} disabled={!txId || busy !== null}
            className="btn-outline">Inspect</button>
          {txConfirm === "resume" ? (
            <button onClick={() => void opResume(txId)} className="btn-danger">
              Confirm resume
            </button>
          ) : (
            <button onClick={() => setTxConfirm("resume")} disabled={!txId || busy !== null}
              className="btn-outline text-destructive">
              <Wrench size={13} /> Resume
            </button>
          )}
        </div>
        <div className="flex gap-2">
          <input value={txTxn} onChange={(e) => { setTxTxn(e.target.value); setTxConfirm(false); }}
            placeholder="transaction id (from a transaction plan/apply result)"
            className="input w-80 font-mono" />
          <button onClick={() => void txInspect(txTxn)} disabled={!txTxn || busy !== null}
            className="btn-outline">Inspect</button>
          {txConfirm === "tx" ? (
            <button onClick={() => void txRecover(txTxn)} className="btn-danger">
              Confirm recover
            </button>
          ) : (
            <button onClick={() => setTxConfirm("tx")} disabled={!txTxn || busy !== null}
              className="btn-outline text-destructive">
              <Wrench size={13} /> Recover tx
            </button>
          )}
        </div>
        {txResult && (
          <>
            <ResultMeta r={txResult} />
            {txResult.data && <Json v={txResult.data} />}
          </>
        )}
      </section>

      {busy && <Spinner label="Querying target" />}

      {Object.entries(results).map(([k, r]) => (
        <section key={k} className="space-y-2">
          <h2 className="font-mono text-xs font-semibold">{k}</h2>
          <ResultMeta r={r} />
          {r.data && <Json v={r.data} />}
        </section>
      ))}
    </div>
  );
}
