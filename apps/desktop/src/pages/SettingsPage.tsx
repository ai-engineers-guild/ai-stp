import { useApp } from "../store";
import { Json } from "../components/Result";

export default function SettingsPage() {
  const { cliVersion, registryDigest } = useApp();

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
    </div>
  );
}
