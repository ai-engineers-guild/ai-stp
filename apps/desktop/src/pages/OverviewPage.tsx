import { useState } from "react";
import { Link } from "react-router";
import { ArrowRight, RefreshCw, CircleCheck } from "lucide-react";
import { ResultMeta, Spinner, Details } from "../components/Result";
import { ActionLink, PageHeader, StatusBadge } from "../components/Layout";
import { useApp } from "../store";
import { useContexts } from "../contexts";
import { useText, type MessageKey } from "../i18n";

export default function OverviewPage() {
  const t = useText();
  const {
    cliVersion,
    cliOk,
    capabilities,
    doctor,
    location,
    engineResult,
    refreshCli,
  } = useApp();
  const selected = useContexts((state) => state.selected);
  const contextsLoading = useContexts((state) => state.loading);
  const contextsResult = useContexts((state) => state.result);
  const refreshContexts = useContexts((state) => state.refresh);
  const [busy, setBusy] = useState(false);
  async function refresh() {
    setBusy(true);
    try {
      await Promise.all([refreshCli(), refreshContexts(true)]);
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
  const installation = (
    capabilities?.data?.native_configuration as
      { available?: boolean } | undefined
  )?.available;
  const checking = cliOk === null || contextsLoading;
  const next: {
    title: MessageKey;
    help: MessageKey;
    action?: MessageKey;
    to?: string;
  } = checking
    ? { title: "home.checkTitle", help: "home.checkHelp" }
    : !cliOk || doctor?.ok === false
      ? {
          title: "home.repairTitle",
          help: "home.repairHelp",
          action: "home.repairAction",
          to: "/settings",
        }
      : !ready
        ? {
            title: "home.initializeTitle",
            help: "home.initializeHelp",
            action: "home.initializeAction",
            to: "/settings",
          }
        : contextsResult?.ok === false
          ? {
              title: "home.contextUnavailableTitle",
              help: "home.contextUnavailableHelp",
              action: "home.contextUnavailableAction",
              to: "/profiles",
            }
          : !selected
            ? {
                title: "home.contextTitle",
                help: "home.contextHelp",
                action: "home.contextAction",
                to: "/profiles",
              }
            : {
                title: "home.browseTitle",
                help: "home.browseHelp",
                action: "home.browseAction",
                to: "/catalog",
              };
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("common.workspace")}
        title={t("home.title")}
        description={t("home.description")}
        action={
          <button
            className="btn-outline"
            disabled={busy}
            onClick={() => void refresh()}
          >
            <RefreshCw size={14} aria-hidden="true" />
            {t("common.refresh")}
          </button>
        }
      />
      <section className="hero-panel" aria-labelledby="next-step-title">
        <div className="max-w-xl">
          <p className="eyebrow">{t("home.next")}</p>
          <h2 id="next-step-title" className="hero-title">
            {t(next.title)}
          </h2>
          <p className="mt-3 max-w-lg text-sm leading-6 text-muted-foreground">
            {t(next.help)}
          </p>
          {next.to && next.action && (
            <Link className="btn-primary mt-5" to={next.to}>
              {t(next.action)}
              <ArrowRight size={15} aria-hidden="true" />
            </Link>
          )}
          {checking && (
            <div className="mt-4">
              <Spinner label={t("common.checking")} />
            </div>
          )}
        </div>
        {ready && (
          <CircleCheck
            className="hidden shrink-0 text-success lg:block"
            size={48}
            strokeWidth={1.5}
            aria-hidden="true"
          />
        )}
      </section>
      <section
        aria-label={t("home.device")}
        className="grid gap-4 sm:grid-cols-3"
      >
        <div className="stat-card">
          <p className="eyebrow">{t("home.identity")}</p>
          <p className="stat-value">
            {!doctor
              ? t(cliOk === false ? "home.notChecked" : "common.checking")
              : t(ready ? "home.identityReady" : "home.identityNeeded")}
          </p>
          <p className="stat-note" data-testid="engine-version">
            {t("home.engineVersion", { version: cliVersion ?? "—" })}
          </p>
        </div>
        <div className="stat-card">
          <p className="eyebrow">{t("home.context")}</p>
          <p className="stat-value break-words">
            {selected?.label ?? t("home.noContext")}
          </p>
          <p className="stat-note">{t("home.contextHelpShort")}</p>
        </div>
        <div className="stat-card">
          <p className="eyebrow">{t("home.installation")}</p>
          <p className="stat-value">
            {t(
              installation === true
                ? "common.available"
                : capabilities || cliOk === false
                  ? "common.unavailable"
                  : "common.checking",
            )}
          </p>
          <p className="stat-note">{t("home.installationHelp")}</p>
        </div>
      </section>
      {busy && <Spinner label={t("home.refreshing")} />}
      {engineResult && !engineResult.ok && <ResultMeta r={engineResult} />}
      {doctor && !doctor.ok && <ResultMeta r={doctor} />}
      {cliOk && doctor?.ok && contextsResult && !contextsResult.ok && (
        <ResultMeta r={contextsResult} />
      )}
      <section className="grid gap-4 lg:grid-cols-2">
        <ActionLink to="/targets" title={t("home.reviewTitle")}>
          {t("home.reviewHelp")}
        </ActionLink>
        <ActionLink to="/tasks" title={t("home.activityTitle")}>
          {t("home.activityHelp")}
        </ActionLink>
      </section>
      <details className="card p-5">
        <summary className="section-title">{t("home.checks")}</summary>
        <p className="mt-3 text-xs text-muted-foreground">
          {t("home.checksHelp")}
        </p>
        {!doctor && cliOk !== false && <Spinner label={t("home.checkTitle")} />}
        <ul className="mt-3 divide-y divide-border">
          {checks.map((check) => (
            <li key={check.name} className="check-row px-0">
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
        {location?.data && (
          <p className="mt-4 break-all text-xs text-muted-foreground">
            {t("home.localWorkspace")}{" "}
            <code>{String(location.data.state_dir)}</code>
          </p>
        )}
        {capabilities?.data && (
          <Details label={t("home.capabilities")} value={capabilities.data} />
        )}
      </details>
      <Link
        to="/install?intent=author"
        className="inline-flex min-h-9 items-center gap-2 text-sm text-primary hover:underline"
      >
        {t("home.authorTitle")}
        <ArrowRight size={14} aria-hidden="true" />
      </Link>
    </div>
  );
}
