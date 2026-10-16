import { useState } from "react";
import { Link } from "react-router";
import { ArrowRight, RefreshCw, TerminalSquare } from "lucide-react";
import { ResultMeta, Spinner, Details } from "../components/Result";
import { ActionLink, PageHeader, StatusBadge } from "../components/Layout";
import { useApp } from "../store";

export default function OverviewPage() {
  const {
    cliVersion,
    cliOk,
    capabilities,
    doctor,
    location,
    engineResult,
    refreshCli,
  } = useApp();
  const [busy, setBusy] = useState(false);
  async function refresh() {
    setBusy(true);
    try {
      await refreshCli();
    } finally {
      setBusy(false);
    }
  }
  const checks = (doctor?.data?.checks ?? []) as {
    name: string;
    state: string;
    detail: string;
  }[];
  const ready =
    checks.find((check) => check.name === "local_identity")?.state === "ready";
  const installation = capabilities?.data?.configuration_installation;
  return (
    <div className="page-stack">
      <PageHeader
        title="A home for your AI setups"
        description="Configure your tools. Keep your workflow yours."
        action={
          <button
            className="btn-outline"
            disabled={busy}
            onClick={() => void refresh()}
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        }
      />
      <section className="hero-panel">
        <div className="max-w-xl">
          <p className="eyebrow">One workspace. Your harnesses.</p>
          <h2 className="hero-title">
            Good tools deserve
            <br />a considered setup.
          </h2>
          <p className="mt-3 max-w-lg text-sm leading-6 text-muted-foreground">
            Discover complete configurations, create your own, and apply them
            through the native ai-stp engine.
          </p>
          <Link
            className="btn-primary mt-6"
            to={ready ? "/catalog" : "/settings"}
          >
            {ready ? "Explore the catalog" : "Set up this device"}
            <ArrowRight size={15} />
          </Link>
        </div>
        <div className="hero-emblem" aria-hidden="true">
          <TerminalSquare size={60} strokeWidth={1} />
          <span>ai-stp / native</span>
        </div>
      </section>
      <section
        aria-label="Workspace status"
        className="grid grid-cols-1 gap-4 lg:grid-cols-3"
      >
        <div className="stat-card">
          <p className="eyebrow">Engine</p>
          <p className="stat-value">
            {cliOk === null
              ? "Connecting…"
              : cliOk
                ? `Rust ${cliVersion}`
                : "Unavailable"}
          </p>
          <p className="stat-note">
            Bundled native CLI ·{" "}
            {String(capabilities?.data?.os ?? "checking platform")}
          </p>
        </div>
        <div className="stat-card">
          <p className="eyebrow">Local identity</p>
          <p className="stat-value">
            {!doctor
              ? cliOk === false
                ? "Not checked"
                : "Checking…"
              : ready
                ? "Ready to work"
                : "Setup needed"}
          </p>
          <p className="stat-note">
            {ready
              ? "Shared with your command-line workspace"
              : "Initialize explicitly in Settings"}
          </p>
        </div>
        <div className="stat-card">
          <p className="eyebrow">Setup installation</p>
          <p className="stat-value">
            {installation === "supported"
              ? "Available"
              : installation
                ? "Unavailable"
                : "Checking…"}
          </p>
          <p className="stat-note">
            {installation === "supported"
              ? "Isolated execution, durable recovery"
              : "Availability is reported by the CLI"}
          </p>
        </div>
      </section>
      {busy && <Spinner label="Refreshing workspace status" />}
      {engineResult && !engineResult.ok && <ResultMeta r={engineResult} />}
      {doctor && !doctor.ok && <ResultMeta r={doctor} />}
      <section className="grid gap-4 lg:grid-cols-2">
        <ActionLink to="/install?intent=author" title="Make it your own">
          Create a component and setup from your local files.
        </ActionLink>
        <ActionLink to="/tasks" title="Pick up where you left off">
          Inspect and resume work retained by the engine.
        </ActionLink>
      </section>
      <section className="card overflow-hidden">
        <div className="panel-heading">
          <h2 className="section-title">Environment checks</h2>
          <span className="text-xs text-muted-foreground">
            Read-only diagnostics
          </span>
        </div>
        {!doctor && cliOk !== false && (
          <div className="p-5">
            <Spinner label="Checking this device" />
          </div>
        )}
        <ul className="divide-y divide-border">
          {checks.map((check) => (
            <li key={check.name} className="check-row">
              <div className="min-w-0">
                <p className="text-sm font-medium capitalize">
                  {check.name.replaceAll("_", " ")}
                </p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {check.detail}
                </p>
              </div>
              <StatusBadge state={check.state} />
            </li>
          ))}
        </ul>
      </section>
      {location?.data && (
        <p className="break-all text-xs text-muted-foreground">
          Local workspace <code>{String(location.data.state_dir)}</code>
        </p>
      )}
      {capabilities?.data && (
        <Details label="Engine capabilities" value={capabilities.data} />
      )}
    </div>
  );
}
