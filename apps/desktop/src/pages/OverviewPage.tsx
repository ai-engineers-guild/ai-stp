import { useEffect, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import { cmdCapabilities, cmdDoctor, cmdDeviceShow, type CmdResult } from "../transport";
import { Json, ResultMeta, Spinner } from "../components/Result";
import { useApp } from "../store";

export default function OverviewPage() {
  const { cliVersion, cliOk, registryDigest, refreshCli } = useApp();
  const [caps, setCaps] = useState<CmdResult | null>(null);
  const [doctor, setDoctor] = useState<CmdResult | null>(null);
  const [device, setDevice] = useState<CmdResult | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    await refreshCli();
    setCaps(await cmdCapabilities());
    setDoctor(await cmdDoctor());
    setDevice(await cmdDeviceShow());
    setBusy(false);
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <div className="space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="page-title">Overview</h1>
          <p className="text-sm text-muted-foreground">CLI engine health and environment checks.</p>
        </div>
        <button
          onClick={() => void refresh()}
          className="flex items-center gap-2 rounded-lg border border-input px-3 py-1.5 text-sm hover:bg-accent dark:hover:bg-accent"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </header>

      <section className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="card p-4">
          <p className="text-xs uppercase text-muted-foreground">CLI engine</p>
          <p className="mt-1 text-lg font-semibold">
            {cliOk === null ? "…" : cliOk ? cliVersion || "connected" : "not found"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {cliOk ? "The app drives operations through ai-stp --json" : "Install ai-stp or bundle it as a sidecar"}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs uppercase text-muted-foreground">Command registry</p>
          <p className="mt-1 truncate font-mono text-xs">{registryDigest ?? "—"}</p>
          <p className="mt-1 text-xs text-muted-foreground">Digest-keyed cache of machine descriptors</p>
        </div>
        <div className="card p-4">
          <p className="text-xs uppercase text-muted-foreground">Doctor</p>
          <p className="mt-1 text-lg font-semibold">{doctor ? (doctor.ok ? "healthy" : "issues") : "…"}</p>
          <p className="mt-1 text-xs text-muted-foreground">Environment and dependency checks</p>
        </div>
      </section>

      {busy && <Spinner />}

      {device?.data && (
        <section>
          <h2 className="mb-2 flex items-center gap-2 section-title">
            <Activity size={14} /> Device identity
          </h2>
          <Json v={device.data} />
        </section>
      )}
      {doctor && !doctor.ok && <ResultMeta r={doctor} />}
      {caps && !caps.ok && <ResultMeta r={caps} />}
      {doctor?.data && (
        <section>
          <h2 className="mb-2 section-title">Checks</h2>
          <Json v={doctor.data} />
        </section>
      )}
    </div>
  );
}
