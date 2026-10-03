import { useCallback, useEffect, useMemo, useState } from "react";
import { MonitorSmartphone, RefreshCw } from "lucide-react";
import { cmdRunRead, type CmdResult } from "../transport";
import { ResultMeta, Spinner } from "../components/Result";

interface HarnessInstallation {
  path: string;
  version: string;
  surface: string;
  reason: string;
}

interface Harness {
  harness_id: string;
  title: string;
  support: string;
  state: string;
  installations: HarnessInstallation[];
  configuration: string | null;
  reason: string;
}

interface NativeComponent {
  component_type: string;
  harness_id: string | null;
  scope: string;
  source_path: string;
  holds_secret: boolean;
  // The CLI-computed registration join (`component_source_binding` key).
  // `undefined` on a CLI that predates the field — unknown, not unregistered.
  registered_stable_id?: string | null;
  provenance?: { kind: string; state: string } | null;
}

interface RegistryEntry {
  stable_id: string;
  lane: string;
  fields: {
    component_type?: string;
    harness_id?: string;
    scope?: string;
    source_path?: string;
    source_name?: string;
    name?: string;
    source_root?: string;
    source_repository?: string;
    candidate_id?: string;
  };
}

interface Row {
  kind: string;
  name: string;
  scope: string;
  harness: string;
  path: string;
  stp: string;
  secret: boolean;
}

function basename(p: string): string {
  const parts = p.replace(/\\/g, "/").split("/").filter(Boolean);
  return parts[parts.length - 1] ?? p;
}

/** Machine inventory: which harnesses are installed (every detected
 *  installation, cli and desktop surfaces) and which native components
 *  exist vs which are already registered STP objects. All reads through
 *  the gated `cli_run_read` path — nothing is written. */
export default function DiscoveryPage() {
  const [harnessRes, setHarnessRes] = useState<CmdResult | null>(null);
  const [nativeRes, setNativeRes] = useState<CmdResult | null>(null);
  const [registryRes, setRegistryRes] = useState<CmdResult | null>(null);
  const [kind, setKind] = useState<string>("all");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const [h, n, r] = await Promise.all([
        cmdRunRead("toolchain harnesses"),
        cmdRunRead("component discover"),
        cmdRunRead("component find", {}, ["include-unverified"]),
      ]);
      setHarnessRes(h);
      setNativeRes(n);
      setRegistryRes(r);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const harnesses = useMemo(
    () => ((harnessRes?.data?.harnesses as Harness[] | undefined) ?? []),
    [harnessRes],
  );

  const natives = useMemo(
    () => ((nativeRes?.data?.components as NativeComponent[] | undefined) ?? []),
    [nativeRes],
  );

  const registered = useMemo(() => {
    const data = registryRes?.data ?? {};
    const lanes = ["authoritative", "experimental", "local_owner_or_pinned"];
    const byStableId = new Map<string, RegistryEntry>();
    for (const lane of lanes) {
      const items = (data[lane] as RegistryEntry[] | undefined) ?? [];
      for (const item of items) byStableId.set(item.stable_id, item);
    }
    return byStableId;
  }, [registryRes]);

  const rows = useMemo(() => {
    const seen = new Set<string>();
    const out: Row[] = natives.map((c) => {
      // The registration answer is the CLI's own binding join — never a path
      // comparison: `source_path` is a display string (home-redacted) while
      // passports record a layout-relative tail, so spellings cannot match.
      if (c.registered_stable_id) seen.add(c.registered_stable_id);
      const hit = c.registered_stable_id
        ? registered.get(c.registered_stable_id)
        : undefined;
      return {
        kind: c.component_type,
        name: basename(c.source_path),
        scope: c.scope,
        harness: c.harness_id ?? "—",
        path: c.source_path,
        stp:
          c.registered_stable_id === undefined
            ? "unknown" // CLI predates the field — say so rather than guess
            : c.registered_stable_id === null
              ? "native"
              : (hit?.lane ?? "registered"),
        secret: c.holds_secret,
      };
    });
    for (const [stableId, item] of registered) {
      if (seen.has(stableId)) continue;
      const f = item.fields ?? {};
      const label = f.source_name ?? f.name ?? basename(f.source_path ?? "");
      const imported = !!(f.candidate_id || f.source_repository);
      out.push({
        kind: f.component_type ?? "?",
        name: label || stableId,
        scope: f.scope ?? "—",
        harness: f.harness_id ?? "—",
        path: f.source_root ?? f.source_path ?? "",
        stp: imported ? `${item.lane} (imported)` : `${item.lane} (not seen)`,
        secret: false,
      });
    }
    return out;
  }, [natives, registered]);

  const kinds = useMemo(() => {
    const set = new Map<string, number>();
    for (const r of rows) set.set(r.kind, (set.get(r.kind) ?? 0) + 1);
    return [...set.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [rows]);

  const visible = kind === "all" ? rows : rows.filter((r) => r.kind === kind);

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="page-title">Discovery</h1>
          <p className="text-sm text-muted-foreground">
            What this machine already runs: every detected harness installation
            and native component vs what is already an STP object.
          </p>
        </div>
        <button onClick={() => void refresh()} disabled={busy} className="btn-outline shrink-0">
          <RefreshCw size={13} className={busy ? "animate-spin" : undefined} /> Refresh
        </button>
      </header>

      <section className="card space-y-2 p-4">
        <h2 className="section-title">Harnesses</h2>
        {harnessRes && !harnessRes.ok && <ResultMeta r={harnessRes} />}
        <div className="overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr className="border-b border-border">
                <th className="py-1.5 pr-3 font-medium">Harness</th>
                <th className="py-1.5 pr-3 font-medium">State</th>
                <th className="py-1.5 pr-3 font-medium">Surface</th>
                <th className="py-1.5 pr-3 font-medium">Version</th>
                <th className="py-1.5 pr-3 font-medium">Path</th>
                <th className="py-1.5 font-medium">Config</th>
              </tr>
            </thead>
            <tbody>
              {harnesses.map((h) =>
                h.installations.length === 0 ? (
                  <tr key={h.harness_id} className="border-b border-border/50">
                    <td className="py-1.5 pr-3 font-medium">
                      {h.title}
                      <span className="ml-1.5 font-mono text-[10px] text-muted-foreground">
                        {h.harness_id}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3 text-muted-foreground">{h.state}</td>
                    <td colSpan={4} className="py-1.5 text-muted-foreground">
                      not found on this machine
                    </td>
                  </tr>
                ) : (
                  h.installations.map((inst, i) => (
                    <tr key={`${h.harness_id}-${i}`} className="border-b border-border/50">
                      {i === 0 && (
                        <td className="py-1.5 pr-3 font-medium" rowSpan={h.installations.length}>
                          {h.title}
                          <span className="ml-1.5 font-mono text-[10px] text-muted-foreground">
                            {h.harness_id}
                          </span>
                        </td>
                      )}
                      <td className="py-1.5 pr-3">
                        {i === 0 ? h.state : <span className="text-muted-foreground">″</span>}
                      </td>
                      <td className="py-1.5 pr-3">
                        <span
                          className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
                            inst.surface === "desktop"
                              ? "bg-sky-600/20 text-sky-400"
                              : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {inst.surface}
                        </span>
                      </td>
                      <td className="py-1.5 pr-3 font-mono">{inst.version}</td>
                      <td className="py-1.5 pr-3 font-mono text-muted-foreground">{inst.path}</td>
                      {i === 0 && (
                        <td className="py-1.5 font-mono text-muted-foreground" rowSpan={h.installations.length}>
                          {h.configuration ?? "—"}
                        </td>
                      )}
                    </tr>
                  ))
                ),
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card space-y-2 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="section-title">Components</h2>
          <button
            onClick={() => setKind("all")}
            className={`rounded-full border px-2.5 py-0.5 text-[11px] ${
              kind === "all" ? "border-primary text-primary" : "border-input text-muted-foreground"
            }`}
          >
            all ({rows.length})
          </button>
          {kinds.map(([k, n]) => (
            <button
              key={k}
              onClick={() => setKind(k)}
              className={`rounded-full border px-2.5 py-0.5 text-[11px] ${
                kind === k ? "border-primary text-primary" : "border-input text-muted-foreground"
              }`}
            >
              {k} ({n})
            </button>
          ))}
        </div>
        {(nativeRes && !nativeRes.ok && <ResultMeta r={nativeRes} />)}
        {(registryRes && !registryRes.ok && <ResultMeta r={registryRes} />)}
        <div className="overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr className="border-b border-border">
                <th className="py-1.5 pr-3 font-medium">Type</th>
                <th className="py-1.5 pr-3 font-medium">Name</th>
                <th className="py-1.5 pr-3 font-medium">Scope</th>
                <th className="py-1.5 pr-3 font-medium">Harness</th>
                <th className="py-1.5 pr-3 font-medium">STP</th>
                <th className="py-1.5 font-medium">Path</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r, i) => (
                <tr key={`${r.path}-${i}`} className="border-b border-border/50">
                  <td className="py-1.5 pr-3 font-mono">{r.kind}</td>
                  <td className="py-1.5 pr-3">
                    {r.name}
                    {r.secret && (
                      <span className="ml-1.5 rounded bg-warning/20 px-1 font-mono text-[10px] text-warning">
                        secret
                      </span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3">{r.scope}</td>
                  <td className="py-1.5 pr-3 font-mono">{r.harness}</td>
                  <td className="py-1.5 pr-3">
                    <span
                      className={
                        r.stp === "native" ? "text-muted-foreground" : "text-success"
                      }
                    >
                      {r.stp}
                    </span>
                  </td>
                  <td className="py-1.5 font-mono text-muted-foreground">{r.path}</td>
                </tr>
              ))}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-3 text-muted-foreground">
                    {nativeRes === null ? "…" : "nothing discovered"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {busy && <Spinner label="Scanning machine" />}
      {nativeRes?.data?.complete === false && (
        <p className="text-xs text-muted-foreground">
          <MonitorSmartphone size={11} className="mr-1 inline" />
          Component scan is partial — the CLI returned a continuation cursor.
        </p>
      )}
      {registryRes?.data?.truncated === true && (
        <p className="text-xs text-muted-foreground">
          <MonitorSmartphone size={11} className="mr-1 inline" />
          Registry listing was cut at the engine's bound — some registered
          objects are not shown.
        </p>
      )}
    </div>
  );
}
