import { useEffect, useState } from "react";
import {
  cmdAuthStatus,
  cmdCapabilities,
  cmdDoctor,
  cmdVersion,
  type CmdResult,
} from "./transport";

interface Probe {
  label: string;
  run: () => Promise<CmdResult>;
}

const PROBES: Probe[] = [
  { label: "version", run: cmdVersion },
  { label: "capabilities", run: cmdCapabilities },
  { label: "doctor", run: cmdDoctor },
  { label: "auth status", run: cmdAuthStatus },
];

export function App() {
  const [results, setResults] = useState<Record<string, CmdResult>>({});
  const [pending, setPending] = useState(false);

  useEffect(() => {
    setPending(true);
    let cancelled = false;
    Promise.all(
      PROBES.map(async (p) => [p.label, await p.run()] as const),
    ).then((entries) => {
      if (!cancelled) {
        setResults(Object.fromEntries(entries));
        setPending(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto max-w-3xl p-8 font-sans">
      <h1 className="text-2xl font-semibold">ai-stp</h1>
      <p className="mt-1 text-sm opacity-70">
        Desktop spike — CLI contract verification via{" "}
        <code>ai-stp --json</code>
      </p>
      {pending && <p className="mt-4 text-sm">Probing CLI…</p>}
      <dl className="mt-6 space-y-4">
        {PROBES.map((p) => {
          const r = results[p.label];
          return (
            <div key={p.label} className="rounded-lg border p-4">
              <dt className="text-sm font-medium">
                {p.label}{" "}
                {r && (
                  <span className={r.ok ? "text-green-700" : "text-red-700"}>
                    {r.ok ? "ok" : "failed"}
                  </span>
                )}
              </dt>
              {r?.error && (
                <dd className="mt-1 text-sm text-red-700">{r.error}</dd>
              )}
              {r && r.warnings.length > 0 && (
                <dd className="mt-1 text-sm text-amber-700">
                  {r.warnings.join("; ")}
                </dd>
              )}
              {r?.data && (
                <dd className="mt-2">
                  <pre className="overflow-x-auto rounded bg-black/5 p-2 text-xs">
                    {JSON.stringify(r.data, null, 2)}
                  </pre>
                </dd>
              )}
            </div>
          );
        })}
      </dl>
    </main>
  );
}
