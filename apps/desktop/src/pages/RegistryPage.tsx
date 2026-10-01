import { useEffect, useState } from "react";
import { cmdMachineHelp, cmdRunRead, type CmdResult } from "../transport";
import { Json, ResultMeta, Spinner } from "../components/Result";

interface Param {
  name: string;
  flag?: string;
  positional?: boolean;
  type?: string;
  required?: boolean;
  choices?: string[];
}

interface Descriptor {
  path: string[];
  summary: string;
  mutability: string;
  confirmation?: string;
  parameters?: Param[];
}

/** The CLI's command surface, rendered from `help --agent --json` — the app
 *  discovers operations instead of hard-coding them. Read-only commands can
 *  be executed directly; mutations are shown but gated. */
export default function RegistryPage() {
  const [help, setHelp] = useState<CmdResult | null>(null);
  const [filter, setFilter] = useState("");
  const [result, setResult] = useState<CmdResult | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void (async () => setHelp(await cmdMachineHelp()))();
  }, []);

  const commands = (((help?.data ?? {}) as Record<string, unknown>).commands ?? []) as Descriptor[];
  const shown = commands.filter(
    (c) =>
      !filter ||
      c.path.join(" ").includes(filter) ||
      c.summary.toLowerCase().includes(filter.toLowerCase()),
  );

  async function runRead(path: string) {
    setBusy(true);
    setResult(await cmdRunRead(path));
    setBusy(false);
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-bold">Command registry</h1>
        <p className="text-sm opacity-60">
          Everything the CLI exposes, generated from machine help. Read commands are runnable; mutations require the dedicated flows.
        </p>
      </header>

      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter commands…"
        className="w-72 rounded-lg border border-current/20 bg-transparent px-3 py-1.5 text-sm"
      />

      {!help && <Spinner />}
      {help && !help.ok && <ResultMeta r={help} />}

      <ul className="divide-y divide-current/10 rounded-xl border border-current/15 text-sm">
        {shown.map((c, i) => {
          const path = c.path.join(" ");
          const mutColor =
            c.mutability === "read"
              ? "bg-emerald-500/15 text-emerald-600"
              : c.mutability === "apply" || c.mutability === "destructive"
                ? "bg-red-500/15 text-red-500"
                : "bg-amber-500/15 text-amber-600";
          return (
            <li key={i} className="flex items-center gap-3 px-4 py-2">
              <span className={`w-24 shrink-0 rounded px-1.5 py-0.5 text-center text-[10px] font-semibold ${mutColor}`}>
                {c.mutability}
              </span>
              <span className="w-56 shrink-0 font-mono text-xs">{path}</span>
              <span className="flex-1 truncate text-xs opacity-70">{c.summary}</span>
              {c.confirmation === "exact_digest" && (
                <span className="rounded bg-red-500/10 px-1.5 text-[10px] text-red-500">digest</span>
              )}
              {c.mutability === "read" ? (
                <button
                  onClick={() => void runRead(path)}
                  disabled={busy}
                  className="rounded border border-current/20 px-2 py-0.5 text-xs hover:bg-black/5 disabled:opacity-40 dark:hover:bg-white/5"
                >
                  run
                </button>
              ) : (
                <span className="px-2 text-[10px] opacity-40">gated</span>
              )}
            </li>
          );
        })}
      </ul>

      {result && (
        <section className="space-y-2">
          <ResultMeta r={result} />
          {result.data && <Json v={result.data} />}
        </section>
      )}
    </div>
  );
}
