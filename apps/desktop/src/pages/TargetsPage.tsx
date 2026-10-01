import { useState } from "react";
import { HardDrive, RefreshCw } from "lucide-react";
import { cmdRunRead, type CmdResult } from "../transport";
import { Json, ResultMeta, Spinner } from "../components/Result";

const HARNESSES = ["antigravity", "claude-code", "codex", "cursor", "grok-build", "opencode", "pi"];

const QUERIES: { label: string; path: string }[] = [
  { label: "Target status", path: "target status" },
  { label: "Backups", path: "target backups" },
  { label: "Diff vs installed", path: "target diff" },
  { label: "Install status", path: "install status" },
  { label: "Update status", path: "update status" },
  { label: "Recoverable ops", path: "install recover" },
];

/** Per-target state: installed footprint, backups, drift, recovery handles.
 *  All reads through the gated `cli_run_read` path — writes stay in flows. */
export default function TargetsPage() {
  const [project, setProject] = useState("");
  const [harness, setHarness] = useState("claude-code");
  const [results, setResults] = useState<Record<string, CmdResult>>({});
  const [busy, setBusy] = useState<string | null>(null);

  async function run(q: (typeof QUERIES)[number]) {
    setBusy(q.path);
    const values: Record<string, string> = { project, harness };
    const r = await cmdRunRead(q.path, values);
    setResults((prev) => ({ ...prev, [q.path]: r }));
    setBusy(null);
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
          Project path
          <input value={project} onChange={(e) => setProject(e.target.value)}
            placeholder="/absolute/path/to/project"
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
            disabled={!project || busy !== null}
            className="flex items-center gap-1.5 rounded-lg border border-input px-3 py-1.5 text-sm hover:bg-accent disabled:text-muted-foreground dark:hover:bg-accent">
            {busy === q.path ? <RefreshCw size={12} className="animate-spin" /> : <HardDrive size={12} />}
            {q.label}
          </button>
        ))}
      </div>

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
