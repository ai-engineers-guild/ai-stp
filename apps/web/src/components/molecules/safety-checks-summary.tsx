import { Badge } from "@/components/atoms/badge";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import type { SafetyChecksSummary as Summary } from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";
import {
  CHECK_IDS,
  extraPercent,
  gatePercent,
  type CheckInfo,
  checkInfoFor,
  isUserFacingCheck,
  policyPercent,
} from "@/lib/safety-checks";
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
  resultDegraded?: string;
  gate?: string;
  extra?: string;
  summary?: string;
  checksComplete?: string;
  expand?: string;
  documentation?: string;
  why?: string;
  help?: string;
  findings: string;
  rules: string;
  paths: string;
  payloadHidden: string;
  checkInfo?: Record<string, CheckInfo>;
};

export function safetyChecksLabels(t: (key: string) => string): Labels {
  const checkInfo: Record<string, CheckInfo> = {};
  for (const id of CHECK_IDS) {
    const name = t(`safetyCheck.${id}.name`);
    const description = t(`safetyCheck.${id}.description`);
    if (name && !name.startsWith("safetyCheck.")) {
      checkInfo[id] = { name, description };
    }
  }
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
    resultDegraded: t("safetyResultDegraded"),
    gate: t("safetyGate"),
    extra: t("safetyExtra"),
    summary: t("safetySummary"),
    checksComplete: t("safetyChecksComplete"),
    expand: t("safetyExpand"),
    documentation: t("safetyDocumentation"),
    why: t("safetyWhy"),
    help: t("safetyHelp"),
    findings: t("safetyFindings"),
    rules: t("safetyRules"),
    paths: t("safetyPaths"),
    payloadHidden: t("safetyPayloadHidden"),
    checkInfo,
  };
}

export function safetyCheckName(checkId: string, localized?: Record<string, CheckInfo>): string {
  return checkInfoFor(checkId, localized).name;
}

function resultLabel(result: Summary["checks"][number]["result"], labels: Labels): string {
  if (result === "passed") return labels.resultPassed;
  if (result === "failed") return labels.resultFailed;
  if (result === "warning") return labels.resultWarning;
  if (result === "degraded") return labels.resultDegraded ?? "Degraded";
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

function resultBadgeVariant(
  result: Summary["checks"][number]["result"],
): "success" | "destructive" | "warning" | "outline" {
  if (result === "passed") return "success";
  if (result === "failed") return "destructive";
  if (result === "warning") return "warning";
  return "outline";
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
  const percent = policyPercent(summary);
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

  const shown = summary.passed + summary.failed + summary.warning;
  const headerSummary = `${summary.passed} / ${shown} ${checksComplete}`;

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
      <SafetyChecksBody
        summary={summary}
        labels={labels}
        summaryText={summaryText}
        whyLabel={whyLabel}
        percent={percent}
      />
    </DetailAccordion>
  );
}

function SafetyChecksBody({
  summary,
  labels,
  summaryText,
  whyLabel,
  percent,
}: {
  summary: Summary;
  labels: Labels;
  summaryText: string;
  whyLabel: string;
  percent: number | null;
}) {
  const checks = summary.checks.filter(isUserFacingCheck);
  const highlightChecks = [...checks]
    .filter((check) => check.result === "failed" || check.result === "warning")
    .sort((left, right) => Number(right.result === "failed") - Number(left.result === "failed"));
  const gate = gatePercent(checks);
  const extra = extraPercent(checks);
  const notRun = checks.filter((check) => check.result === "not_run").length;
  return (
    <div className="space-y-5">
      <p className="text-muted-foreground text-sm">{summaryText}</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatusTile label={labels.passed} value={summary.passed} tone="text-success" icon="check" />
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
          value={notRun}
          tone="text-muted-foreground"
          icon="clock"
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={statusVariant(summary.status)}>{statusLabel(summary.status, labels)}</Badge>
        <span className="font-mono text-sm tabular-nums">
          {percent === null ? "—" : `${percent}%`}
        </span>
      </div>
      {gate !== null || extra !== null ? (
        <ul className="text-muted-foreground space-y-1 text-sm">
          {gate !== null ? (
            <li>
              {labels.gate ?? "Publication gate"}:{" "}
              <span className="text-foreground font-mono tabular-nums">{gate}%</span>
            </li>
          ) : null}
          {extra !== null ? (
            <li>
              {labels.extra ?? "Extra scanners"}:{" "}
              <span className="text-foreground font-mono tabular-nums">{extra}%</span>
            </li>
          ) : null}
        </ul>
      ) : null}
      {highlightChecks.length > 0 ? (
        <ul className="space-y-2">
          {highlightChecks.map((check) => (
            <li
              key={`highlight-${check.check_id}-${check.source}`}
              className={`${resultTone(check.result)} flex gap-2 text-sm`}
            >
              <ResultIcon result={check.result} />
              <span>
                <b>{checkInfoFor(check.check_id, labels.checkInfo).name}:</b>{" "}
                {checkReason(check, labels)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {checks.length > 0 ? (
        <ul className="divide-border border-border divide-y rounded-sm border">
          {checks.map((check) => {
            const info = checkInfoFor(check.check_id, labels.checkInfo);
            const description = info.description || check.family;
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
                      <Badge variant={resultBadgeVariant(check.result)}>
                        {resultLabel(check.result, labels)}
                      </Badge>
                      {check.mandatory ? (
                        <span className="text-muted-foreground text-xs">{labels.mandatory}</span>
                      ) : null}
                    </div>
                    <p className="text-muted-foreground mt-1 text-sm">{description}</p>
                    <code className="text-muted-foreground mt-1 block text-[11px] break-all">
                      {check.check_id}
                    </code>
                    {needsReason ? (
                      <CheckFindingDetails check={check} labels={labels} whyLabel={whyLabel} />
                    ) : null}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

function CheckFindingDetails({
  check,
  labels,
  whyLabel,
}: {
  check: Summary["checks"][number];
  labels: Labels;
  whyLabel: string;
}) {
  const finding = check.finding_summary;
  const failed = check.result === "failed";
  if (!finding)
    return (
      <p className={`${failed ? "text-destructive" : "text-warning"} mt-2 flex gap-2 text-sm`}>
        <Icon name="alert" size="sm" />
        <span>
          <b>{whyLabel}:</b> {checkReason(check, labels)}
        </span>
      </p>
    );
  return (
    <div
      className={`${
        failed ? "border-destructive/40 bg-destructive/5" : "border-warning/40 bg-warning/5"
      } mt-3 space-y-2 rounded-sm border p-3 text-sm`}
    >
      <p>
        <b>{labels.findings}:</b> {finding.count}
      </p>
      {finding.rule_ids.length ? (
        <p>
          <b>{labels.rules}:</b> <code>{finding.rule_ids.join(", ")}</code>
        </p>
      ) : null}
      {finding.paths.length ? (
        <p>
          <b>{labels.paths}:</b> <code>{finding.paths.join(", ")}</code>
        </p>
      ) : null}
      <p className="text-muted-foreground">{labels.payloadHidden}</p>
    </div>
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
