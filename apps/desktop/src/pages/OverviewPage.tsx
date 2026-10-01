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
          <h1 className="text-xl font-bold">Overview</h1>
          <p className="text-sm opacity-60">CLI engine health and environment checks.</p>
        </div>
        <button
          onClick={() => void refresh()}
          className="flex items-center gap-2 rounded-lg border border-current/20 px-3 py-1.5 text-sm hover:bg-black/5 dark:hover:bg-white/5"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </header>

      <section className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded-xl border border-current/15 p-4">
          <p className="text-xs uppercase opacity-50">CLI engine</p>
          <p className="mt-1 text-lg font-semibold">
            {cliOk === null ? "…" : cliOk ? cliVersion || "connected" : "not found"}
          </p>
          <p className="mt-1 text-xs opacity-60">
            {cliOk ? "The app drives operations through ai-stp --json" : "Install ai-stp or bundle it as a sidecar"}
          </p>
        </div>
        <div className="rounded-xl border border-current/15 p-4">
          <p className="text-xs uppercase opacity-50">Command registry</p>
          <p className="mt-1 truncate font-mono text-xs">{registryDigest ?? "—"}</p>
          <p className="mt-1 text-xs opacity-60">Digest-keyed cache of machine descriptors</p>
        </div>
        <div className="rounded-xl border border-current/15 p-4">
          <p className="text-xs uppercase opacity-50">Doctor</p>
          <p className="mt-1 text-lg font-semibold">{doctor ? (doctor.ok ? "healthy" : "issues") : "…"}</p>
          <p className="mt-1 text-xs opacity-60">Environment and dependency checks</p>
        </div>
      </section>

      {busy && <Spinner />}

      {device?.data && (
        <section>
          <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Activity size={14} /> Device identity
          </h2>
          <Json v={device.data} />
        </section>
      )}
      {doctor && !doctor.ok && <ResultMeta r={doctor} />}
      {caps && !caps.ok && <ResultMeta r={caps} />}
      {doctor?.data && (
        <section>
          <h2 className="mb-2 text-sm font-semibold">Checks</h2>
          <Json v={doctor.data} />
        </section>
      )}
    </div>
  );
}
