import { useApp } from "../store";
import { Json } from "../components/Result";

export default function SettingsPage() {
  const { scope, setScope, cliVersion, registryDigest } = useApp();

  return (
    <div className="space-y-5">
      <header>
        <h1 className="page-title">Settings</h1>
      </header>

      <section className="space-y-3 card p-4">
        <h2 className="section-title">Scope</h2>
        <p className="text-xs text-muted-foreground">
          “All” is a read-only aggregation; writes require an explicit target.
        </p>
        <div className="flex gap-2">
          {(["all", "global", "project"] as const).map((k) => (
            <button
              key={k}
              onClick={() =>
                setScope(k === "project" ? { kind: "project", path: "" } : { kind: k })
              }
              className={`rounded-lg border px-3 py-1.5 text-sm ${
                scope.kind === k
                  ? "border-primary bg-primary/10 font-medium text-primary"
                  : "border-current/20 text-muted-foreground"
              }`}
            >
              {k === "all" ? "All (read-only)" : k}
            </button>
          ))}
        </div>
        {scope.kind === "project" && (
          <input
            value={scope.path}
            onChange={(e) => setScope({ kind: "project", path: e.target.value })}
            placeholder="/absolute/path/to/project"
            className="w-full rounded-lg border border-input bg-transparent px-3 py-1.5 font-mono text-sm"
          />
        )}
      </section>

      <section className="space-y-2 card p-4">
        <h2 className="section-title">CLI engine</h2>
        <Json
          v={{
            version: cliVersion,
            registry_digest: registryDigest,
            resolution: "bundled sidecar → $AI_STP_CLI → PATH",
          }}
        />
        <p className="text-xs text-muted-foreground">
          A missing pinned binary is an error, never a silent fallback to an
          arbitrary executable.
        </p>
      </section>
    </div>
  );
}
