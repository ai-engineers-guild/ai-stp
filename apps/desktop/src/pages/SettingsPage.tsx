import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Save } from "lucide-react";
import { useApp } from "../store";
import { cliApplyConfirmed, cmdRunRead, type CmdResult } from "../transport";
import { Json, ResultMeta, Spinner } from "../components/Result";

interface ConfigValue {
  path: string;
  value: unknown;
  source: string;
}

/** Configuration surface: the platform endpoint the CLI talks to, plus the
 *  full effective-config table the CLI computes (value + origin). `config set`
 *  is an apply-tier command — the Save button is the explicit confirmation. */
export default function SettingsPage() {
  const { cliVersion, registryDigest } = useApp();
  const [cfg, setCfg] = useState<CmdResult | null>(null);
  const [host, setHost] = useState("");
  const [saved, setSaved] = useState<CmdResult | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const r = await cmdRunRead("config show");
    setCfg(r);
    const values = (r.data?.values as ConfigValue[] | undefined) ?? [];
    const url = values.find((v) => v.path === "catalog.url");
    if (url && typeof url.value === "string" && !host) setHost(url.value);
  }, [host]);

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function saveHost() {
    setBusy(true);
    setSaved(null);
    try {
      const r = await cliApplyConfirmed(
        "config set",
        { set: `catalog.url=${host.trim()}` },
        [],
        true,
      );
      setSaved(r);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  const values = (cfg?.data?.values as ConfigValue[] | undefined) ?? [];

  return (
    <div className="space-y-5">
      <header>
        <h1 className="page-title">Settings</h1>
      </header>

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

      <section className="space-y-2 card p-4">
        <h2 className="section-title">Platform</h2>
        <p className="text-xs text-muted-foreground">
          Where `catalog.url` points: the `/v1` platform used by Catalog, sign-in
          and sync. Written to the CLI's config file through the apply gate.
        </p>
        <div className="flex max-w-xl gap-2">
          <input
            value={host}
            onChange={(e) => setHost(e.target.value)}
            placeholder="https://platform.example.com"
            className="input flex-1 font-mono"
          />
          <button
            onClick={() => void saveHost()}
            disabled={busy || !host.trim()}
            className="btn-outline"
          >
            <Save size={13} /> Save
          </button>
        </div>
        {saved && <ResultMeta r={saved} />}
      </section>

      <section className="space-y-2 card p-4">
        <div className="flex items-center justify-between">
          <h2 className="section-title">Effective configuration</h2>
          <button onClick={() => void refresh()} className="btn-outline !py-0.5 !text-[11px]">
            <RefreshCw size={11} /> Reload
          </button>
        </div>
        {cfg && !cfg.ok && <ResultMeta r={cfg} />}
        <div className="overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr className="border-b border-border">
                <th className="py-1.5 pr-3 font-medium">Key</th>
                <th className="py-1.5 pr-3 font-medium">Value</th>
                <th className="py-1.5 font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {values.map((v) => (
                <tr key={v.path} className="border-b border-border/50">
                  <td className="py-1.5 pr-3 font-mono">{v.path}</td>
                  <td className="py-1.5 pr-3 font-mono">{JSON.stringify(v.value)}</td>
                  <td className="py-1.5 text-muted-foreground">{v.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {typeof cfg?.data?.config_path === "string" && (
          <p className="font-mono text-[11px] text-muted-foreground">
            {cfg.data.config_path}
          </p>
        )}
        {!cfg && <Spinner label="Reading configuration" />}
      </section>
    </div>
  );
}
