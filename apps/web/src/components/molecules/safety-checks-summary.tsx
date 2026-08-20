import { Badge } from "@/components/atoms/badge";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import type { SafetyChecksSummary as Summary } from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type Labels = {
  title: string;
  status: string;
  percent: string;
  passed: string;
  failed: string;
  warning: string;
  notRun: string;
  incomplete: string;
  empty: string;
  noScan: string;
  available: string;
  pending: string;
  mandatory: string;
  resultPassed: string;
  resultFailed: string;
  resultWarning: string;
  resultNotRun: string;
  summary?: string;
  checksComplete?: string;
  expand?: string;
  documentation?: string;
  why?: string;
  help?: string;
};

export function safetyChecksLabels(t: (key: string) => string): Labels {
  return {
    title: t("safetyChecks"),
    status: t("safetyStatus"),
    percent: t("safetyPercent"),
    passed: t("safetyPassed"),
    failed: t("safetyFailed"),
    warning: t("safetyWarning"),
    notRun: t("safetyNotRun"),
    incomplete: t("safetyIncomplete"),
    empty: t("safetyEmpty"),
    noScan: t("safetyNoScan"),
    available: t("safetyAvailable"),
    pending: t("safetyPending"),
    mandatory: t("safetyMandatory"),
    resultPassed: t("safetyResultPassed"),
    resultFailed: t("safetyResultFailed"),
    resultWarning: t("safetyResultWarning"),
    resultNotRun: t("safetyResultNotRun"),
    summary: t("safetySummary"),
    checksComplete: t("safetyChecksComplete"),
    expand: t("safetyExpand"),
    documentation: t("safetyDocumentation"),
    why: t("safetyWhy"),
    help: t("safetyHelp"),
  };
}

const CHECK_INFO: Record<string, { name: string; description: string }> = {
  structure: {
    name: "Passport structure",
    description: "Validates the passport schema and canonical form.",
  },
  digest: {
    name: "Artifact integrity",
    description: "Recomputes the digest so changed bytes cannot pass as the published version.",
  },
  license: { name: "License", description: "Checks that redistribution terms are declared." },
  tags: { name: "Catalog tags", description: "Validates required normalized catalog tags." },
  source_repo: {
    name: "Source provenance",
    description: "Confirms the exact public repository, commit and path.",
  },
  artifact_unpack: {
    name: "Safe unpacking",
    description: "Unpacks the artifact within size and file-count limits.",
  },
  path_denylist: {
    name: "Dangerous paths",
    description: "Rejects secrets, credentials, device files and unsafe paths.",
  },
  secrets_heuristic: {
    name: "Secret patterns",
    description: "Looks for likely tokens, private keys and credentials.",
  },
  secrets_gitleaks: {
    name: "Gitleaks secret scan",
    description: "Runs the Gitleaks ruleset over the artifact.",
  },
  content_hidden: {
    name: "Hidden content",
    description: "Detects concealed instructions and suspicious invisible content.",
  },
  pi_content_pack: {
    name: "Prompt injection",
    description: "Looks for instructions that attempt to override the agent or exfiltrate data.",
  },
  sast_opengrep: {
    name: "Static code analysis",
    description: "Uses owned Opengrep rules to find unsafe code patterns.",
  },
  skill_static_gate: {
    name: "Agent skill policy",
    description: "Checks skill metadata, permissions and malicious instruction patterns.",
  },
};

function resultLabel(result: Summary["checks"][number]["result"], labels: Labels): string {
  if (result === "passed") return labels.resultPassed;
  if (result === "failed") return labels.resultFailed;
  if (result === "warning") return labels.resultWarning;
  return labels.resultNotRun;
}

function statusVariant(status: Summary["status"]): "success" | "warning" | "secondary" | "outline" {
  if (status === "available") return "success";
  if (status === "pending") return "warning";
  if (status === "incomplete") return "secondary";
  return "outline";
}

function statusLabel(status: Summary["status"], labels: Labels): string {
  if (status === "available") return labels.available;
  if (status === "pending") return labels.pending;
  if (status === "incomplete") return labels.incomplete;
  return labels.empty;
}

function resultTone(result: Summary["checks"][number]["result"]): string {
  if (result === "passed") return "text-success";
  if (result === "failed") return "text-destructive";
  if (result === "warning") return "text-warning";
  return "text-muted-foreground";
}

function ResultIcon({ result }: { result: Summary["checks"][number]["result"] }) {
  const className = `size-4 shrink-0 ${resultTone(result)}`;
  if (result === "passed") return <Icon name="check" className={className} />;
  if (result === "failed") return <Icon name="close" className={className} />;
  if (result === "warning") return <Icon name="alert" className={className} />;
  return <Icon name="clock" className={className} />;
}

function SafetyHelp({
  helpLabel,
  documentationLabel,
}: {
  helpLabel: string;
  documentationLabel: string;
}) {
  return (
    <div className="flex items-center gap-1">
      <Link
        href="/docs/security-checks"
        aria-label={helpLabel}
        className="text-foreground hover:bg-muted focus-visible:ring-ring inline-flex size-11 items-center justify-center rounded-sm focus-visible:ring-2 focus-visible:outline-none"
      >
        <Icon name="help" size="sm" />
      </Link>
      <Link
        href="/docs/security-checks"
        className="text-foreground hover:text-primary focus-visible:ring-ring hidden items-center text-sm underline underline-offset-4 focus-visible:rounded-sm focus-visible:ring-2 focus-visible:outline-none sm:inline-flex"
      >
        {documentationLabel}
      </Link>
    </div>
  );
}

/** Public safety-scan projection for catalog cards and object detail (#270). */
export function SafetyChecksSummaryView({
  summary,
  labels,
  compact = false,
}: {
  summary: Summary | null | undefined;
  labels: Labels;
  compact?: boolean;
}) {
  const documentationLabel = labels.documentation ?? "How checks work";
  const helpLabel = labels.help ?? "About safety checks";
  const help = <SafetyHelp helpLabel={helpLabel} documentationLabel={documentationLabel} />;
  if (!summary)
    return compact ? (
      <Badge variant="outline">{labels.noScan}</Badge>
    ) : (
      <DetailAccordion
        title={labels.title}
        summary={
          <span className="space-y-0.5">
            <span className="block">{labels.noScan}</span>
            <span className="block">{labels.summary}</span>
          </span>
        }
        headerAction={help}
      >
        <p className="text-muted-foreground text-sm">{labels.summary}</p>
      </DetailAccordion>
    );
  const percent = summary.checks_passed_percent;
  const summaryText = labels.summary ?? "Automated checks reduce known risks.";
  const checksComplete = labels.checksComplete ?? "checks passed";
  const whyLabel = labels.why ?? "Why";
  if (compact)
    return (
      <span className="inline-flex flex-wrap items-center gap-1">
        <Badge variant={statusVariant(summary.status)}>{statusLabel(summary.status, labels)}</Badge>
        {percent !== null ? (
          <Badge variant="outline">
            {labels.percent}: {percent}%
          </Badge>
        ) : null}
      </span>
    );

  const headerSummary = `${summary.passed} / ${summary.checks.length} ${checksComplete}`;
  const warningChecks = summary.checks.filter((check) => check.result === "warning");

  return (
    <DetailAccordion
      title={labels.title}
      summary={
        <span className="space-y-0.5">
          <span className="block">{headerSummary}</span>
          <span className="block">{summaryText}</span>
        </span>
      }
      headerAction={help}
    >
      <div className="space-y-5">
        <p className="text-muted-foreground text-sm">{summaryText}</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatusTile
            label={labels.passed}
            value={summary.passed}
            tone="text-success"
            icon="check"
          />
          <StatusTile
            label={labels.warning}
            value={summary.warning}
            tone="text-warning"
            icon="alert"
          />
          <StatusTile
            label={labels.failed}
            value={summary.failed}
            tone="text-destructive"
            icon="close"
          />
          <StatusTile
            label={labels.notRun}
            value={summary.not_run}
            tone="text-muted-foreground"
            icon="clock"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={statusVariant(summary.status)}>
            {statusLabel(summary.status, labels)}
          </Badge>
          <span className="font-mono text-sm tabular-nums">
            {percent === null ? "—" : `${percent}%`}
          </span>
        </div>
        {warningChecks.length > 0 ? (
          <ul className="space-y-2">
            {warningChecks.map((check) => (
              <li
                key={`warn-${check.check_id}-${check.source}`}
                className="text-warning flex gap-2 text-sm"
              >
                <Icon name="alert" size="sm" />
                <span>
                  <b>{CHECK_INFO[check.check_id]?.name ?? check.check_id}:</b>{" "}
                  {checkReason(check, labels)}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        {summary.checks.length > 0 ? (
          <ul className="divide-border border-border divide-y rounded-sm border">
            {summary.checks.map((check) => {
              const info = CHECK_INFO[check.check_id] ?? {
                name: check.check_id,
                description: check.family,
              };
              const needsReason =
                check.result !== "passed" &&
                check.result !== "not_applicable" &&
                check.result !== "skipped";
              return (
                <li key={`${check.check_id}-${check.source}`} className="px-3 py-3">
                  <div className="flex items-start gap-3">
                    <ResultIcon result={check.result} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{info.name}</span>
                        <Badge variant={check.result === "failed" ? "warning" : "outline"}>
                          {resultLabel(check.result, labels)}
                        </Badge>
                        {check.mandatory ? (
                          <span className="text-muted-foreground text-xs">{labels.mandatory}</span>
                        ) : null}
                      </div>
                      <p className="text-muted-foreground mt-1 text-sm">{info.description}</p>
                      <code className="text-muted-foreground mt-1 block text-[11px] break-all">
                        {check.check_id}
                      </code>
                      {needsReason ? (
                        <p className="text-destructive mt-2 flex gap-2 text-sm">
                          <Icon name="alert" size="sm" />
                          <span>
                            <b>{whyLabel}:</b> {checkReason(check, labels)}
                          </span>
                        </p>
                      ) : null}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </DetailAccordion>
  );
}

function checkReason(check: Summary["checks"][number], labels: Labels): string {
  if (typeof check.reason === "string" && check.reason.trim()) return check.reason;
  const detail = (check as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return resultLabel(check.result, labels);
}

function StatusTile({
  label,
  value,
  tone,
  icon,
}: {
  label: string;
  value: number;
  tone: string;
  icon: "check" | "alert" | "close" | "clock";
}) {
  return (
    <div className="bg-muted/30 rounded-sm p-3">
      <p className="text-muted-foreground flex items-center gap-1.5 text-sm">
        <Icon name={icon} size="sm" className={tone} />
        {label}
      </p>
      <p className={`mt-1 font-mono text-lg font-medium tabular-nums ${tone}`}>{value}</p>
    </div>
  );
}
