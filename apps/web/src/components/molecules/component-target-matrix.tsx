import type { SafetyCheckEntry, TargetMatrix } from "@/lib/api/generated/types.gen";
import { Badge } from "@/components/atoms/badge";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme";

export type TargetMatrixLabels = {
  heading: string;
  summary: string;
  score: string;
  harness: string;
  scope: string;
  operatingSystems: string;
  architectures: string;
  implementation: string;
  projectionKind: string;
  technicalSupport: string;
  supportReason: string;
  supportSupported: string;
  supportExperimental: string;
  supportUnsupported: string;
  assessment: string;
  safetyCheck: string;
  projectionDetails: string;
  notVerified: string;
  verified: string;
  failed: string;
  stale: string;
  recommendation: string;
  recommended: string;
  notRecommended: string;
  ineffective: string;
  freshness: string;
  semanticLosses: string;
  permissions: string;
  evidence: string;
  checksNotRecorded: string;
  checkPassed: string;
  checkWarning: string;
  checkFailed: string;
  checkNotRun: string;
  checkIncomplete: string;
  checksComplete: string;
  projections: string;
};

export function targetMatrixLabels(t: (key: string) => string): TargetMatrixLabels {
  return {
    heading: t("targetMatrix"),
    summary: t("targetMatrixSummary"),
    score: t("targetMatrixScore"),
    harness: t("harness"),
    scope: t("targetScope"),
    operatingSystems: t("operatingSystems"),
    architectures: t("architectures"),
    implementation: t("implementationMode"),
    projectionKind: t("projectionKind"),
    technicalSupport: t("technicalSupport"),
    supportReason: t("supportReason"),
    supportSupported: t("supportSupported"),
    supportExperimental: t("supportExperimental"),
    supportUnsupported: t("supportUnsupported"),
    assessment: t("assessmentState"),
    safetyCheck: t("safetyCheckColumn"),
    projectionDetails: t("projectionDetails"),
    notVerified: t("assessmentNotVerified"),
    verified: t("assessmentVerified"),
    failed: t("assessmentFailed"),
    stale: t("assessmentStale"),
    recommendation: t("recommendation"),
    recommended: t("recommendationRecommended"),
    notRecommended: t("recommendationNotRecommended"),
    ineffective: t("recommendationIneffective"),
    freshness: t("freshness"),
    semanticLosses: t("semanticLosses"),
    permissions: t("permissionsSummary"),
    evidence: t("evidenceReferences"),
    checksNotRecorded: t("checksNotRecorded"),
    checkPassed: t("checkPassed"),
    checkWarning: t("checkWarning"),
    checkFailed: t("checkFailed"),
    checkNotRun: t("checkNotRun"),
    checkIncomplete: t("checkIncomplete"),
    checksComplete: t("safetyChecksComplete"),
    projections: t("harnessProjectionsCount"),
  };
}

export function ComponentTargetMatrix({
  matrix,
  labels,
}: {
  matrix?: TargetMatrix | null;
  labels: TargetMatrixLabels;
}) {
  if (!matrix) return null;
  if (matrix.exact.length === 0) return null;
  const score = checkScore(matrix.exact.flatMap(safetyChecksFor));

  return (
    <section
      data-ui={UI.catalog.targetMatrix}
      aria-labelledby="target-matrix-heading"
      className="border-border min-w-0 rounded-lg border"
    >
      <details className="group">
        <summary className="focus-visible:ring-ring flex min-h-20 cursor-pointer list-none items-center gap-3 rounded-lg p-4 focus-visible:ring-2 focus-visible:outline-none [&::-webkit-details-marker]:hidden">
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex min-w-0 items-center gap-2">
              <h2 id="target-matrix-heading" className="font-semibold">
                {labels.heading}
              </h2>
              <span
                className="text-muted-foreground inline-flex size-7 shrink-0 items-center justify-center"
                title={labels.summary}
                aria-label={labels.summary}
              >
                <Icon name="help" size="sm" />
              </span>
            </div>
            <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <Score score={score} />
              <span>
                {score.passed} / {score.total} {labels.checksComplete}
              </span>
              <span>
                {matrix.exact.length} {labels.projections}
              </span>
            </div>
          </div>
          <Icon
            name="chevronDown"
            size="sm"
            className="shrink-0 transition-transform group-open:rotate-180"
          />
        </summary>
        <div className="border-border border-t p-3">
          <MatrixCards matrix={matrix} labels={labels} />
        </div>
      </details>
    </section>
  );
}

function MatrixCards({ matrix, labels }: { matrix: TargetMatrix; labels: TargetMatrixLabels }) {
  return (
    <ul className="space-y-2">
      {matrix.exact.map((row) => (
        <li key={`${row.adaptation_id}:${row.scope}`}>
          <ProjectionDetails row={row} labels={labels} />
        </li>
      ))}
    </ul>
  );
}

function ProjectionDetails({
  row,
  labels,
}: {
  row: TargetMatrix["exact"][number];
  labels: TargetMatrixLabels;
}) {
  const safetyChecks = safetyChecksFor(row);
  const score = checkScore(safetyChecks);

  return (
    <details className="group/row border-border bg-card rounded-lg border shadow-sm">
      <summary className="focus-visible:ring-ring flex min-h-14 min-w-0 cursor-pointer list-none items-center gap-3 rounded-lg p-3 focus-visible:ring-2 focus-visible:outline-none [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 flex-1 font-medium break-words">{row.harness_id}</span>
        <span className="text-muted-foreground hidden text-sm sm:inline">
          {score.passed} / {score.total} {labels.checksComplete}
        </span>
        <Score score={score} />
        <Icon
          name="chevronDown"
          size="sm"
          className="shrink-0 transition-transform group-open/row:rotate-180"
        />
        <span className="sr-only">{labels.projectionDetails}</span>
      </summary>
      <dl className="border-border text-muted-foreground grid gap-3 border-t px-3 py-3 text-xs sm:grid-cols-2">
        <div>
          <dt className="text-foreground font-medium">{labels.safetyCheck}</dt>
          <dd>{assessmentLabel(row.assessment_state, labels)}</dd>
        </div>
        <div>
          <dt className="text-foreground font-medium">{labels.recommendation}</dt>
          <dd>{recommendationLabel(row.recommendation, labels)}</dd>
        </div>
        <div>
          <dt className="text-foreground font-medium">{labels.scope}</dt>
          <dd>{row.scope}</dd>
        </div>
        <div>
          <dt className="text-foreground font-medium">{labels.projectionKind}</dt>
          <dd>{row.projection_kind}</dd>
        </div>
        <div>
          <dt className="text-foreground font-medium">{labels.technicalSupport}</dt>
          <dd>{supportLabel(row.technical_support, labels)}</dd>
        </div>
        <div>
          <dt className="text-foreground font-medium">{labels.implementation}</dt>
          <dd>{row.implementation_mode}</dd>
        </div>
        {row.technical_support_reason ? (
          <div className="sm:col-span-2">
            <dt className="text-foreground font-medium">{labels.supportReason}</dt>
            <dd>{row.technical_support_reason}</dd>
          </div>
        ) : null}
        {row.freshness ? (
          <div>
            <dt className="text-foreground font-medium">{labels.freshness}</dt>
            <dd>{row.freshness}</dd>
          </div>
        ) : null}
        {row.supported_os.length ? (
          <div>
            <dt className="text-foreground font-medium">{labels.operatingSystems}</dt>
            <dd>{row.supported_os.join(", ")}</dd>
          </div>
        ) : null}
        {row.supported_arch.length ? (
          <div>
            <dt className="text-foreground font-medium">{labels.architectures}</dt>
            <dd>{row.supported_arch.join(", ")}</dd>
          </div>
        ) : null}
        {row.permissions_summary.length ? (
          <div className="sm:col-span-2">
            <dt className="text-foreground font-medium">{labels.permissions}</dt>
            <dd>{row.permissions_summary.join(", ")}</dd>
          </div>
        ) : null}
        {row.semantic_losses.length ? (
          <div className="sm:col-span-2">
            <dt className="text-foreground font-medium">{labels.semanticLosses}</dt>
            <dd>{row.semantic_losses.join(", ")}</dd>
          </div>
        ) : null}
        <div className="sm:col-span-2">
          <dt className="text-foreground font-medium">{labels.safetyCheck}</dt>
          {safetyChecks.length ? (
            <dd>
              <ul className="mt-1 space-y-1" aria-label={labels.safetyCheck}>
                {safetyChecks.map((check) => (
                  <li
                    key={check.check_id}
                    className="border-border flex min-w-0 items-start gap-2 rounded-md border px-3 py-2"
                  >
                    <Icon
                      name={checkResultIcon(check.result)}
                      size="sm"
                      className={checkResultTone(check.result)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-medium break-words">{check.check_id}</span>
                        <Badge variant={checkResultVariant(check.result)}>
                          {checkResultLabel(check.result, labels)}
                        </Badge>
                      </span>
                      {check.reason ? (
                        <span className="text-muted-foreground mt-1 block break-words">
                          {check.reason}
                        </span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            </dd>
          ) : (
            <dd>{labels.checksNotRecorded}</dd>
          )}
        </div>
        {row.evidence_refs.length ? (
          <div className="sm:col-span-2">
            <dt className="text-foreground font-medium">{labels.evidence}</dt>
            <dd>
              <ul className="mt-1 space-y-1">
                {row.evidence_refs.map((ref) => (
                  <li key={`${ref.kind}:${ref.value}`} className="break-words">
                    {ref.kind === "url" ? (
                      <a
                        href={ref.value}
                        target="_blank"
                        rel="noreferrer"
                        className="underline underline-offset-2"
                      >
                        {ref.value}
                      </a>
                    ) : (
                      <span>
                        {ref.kind}: {ref.value}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </dd>
          </div>
        ) : null}
      </dl>
    </details>
  );
}

function checkScore(checks: SafetyCheckEntry[]): {
  passed: number;
  total: number;
  percent: number;
} {
  const countable = checks.filter((check) =>
    ["passed", "failed", "warning"].includes(check.result),
  );
  const passed = countable.filter((check) => check.result === "passed").length;
  return {
    passed,
    total: countable.length,
    percent: countable.length ? Math.round((passed / countable.length) * 100) : 0,
  };
}

function safetyChecksFor(row: TargetMatrix["exact"][number]): SafetyCheckEntry[] {
  return (row as unknown as { safety_checks?: SafetyCheckEntry[] }).safety_checks ?? [];
}

function Score({ score }: { score: ReturnType<typeof checkScore> }) {
  return (
    <span
      className="inline-flex items-center gap-1.5"
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={score.percent}
      aria-valuetext={`${score.passed} / ${score.total}`}
    >
      <span className="bg-muted relative block h-1 w-10 overflow-hidden rounded-full" aria-hidden>
        <span
          className="absolute inset-y-0 left-0 overflow-hidden"
          style={{ width: `${score.percent}%` }}
        >
          <span
            className="block h-full w-10"
            style={{
              background:
                "linear-gradient(90deg, hsl(var(--destructive)), hsl(var(--warning)), hsl(var(--success)))",
            }}
          />
        </span>
      </span>
      <span className="font-mono text-sm font-medium tabular-nums">{score.percent}%</span>
    </span>
  );
}

function supportLabel(value: string, labels: TargetMatrixLabels): string {
  if (value === "supported") return labels.supportSupported;
  if (value === "experimental") return labels.supportExperimental;
  return labels.supportUnsupported;
}

function assessmentLabel(value: string, labels: TargetMatrixLabels): string {
  if (value === "verified") return labels.verified;
  if (value === "stale") return labels.stale;
  if (value === "failed") return labels.failed;
  return labels.notVerified;
}

function recommendationLabel(value: string, labels: TargetMatrixLabels): string {
  if (value === "recommended") return labels.recommended;
  if (value === "not_recommended") return labels.notRecommended;
  return labels.ineffective;
}

function checkResultLabel(value: string, labels: TargetMatrixLabels): string {
  if (value === "passed") return labels.checkPassed;
  if (value === "warning") return labels.checkWarning;
  if (value === "failed") return labels.checkFailed;
  if (value === "not_run") return labels.checkNotRun;
  return labels.checkIncomplete;
}

function checkResultTone(value: string): string {
  if (value === "passed") return "text-success";
  if (value === "failed") return "text-destructive";
  if (value === "warning") return "text-warning";
  return "text-muted-foreground";
}

function checkResultIcon(value: string): "check" | "close" | "alert" | "clock" {
  if (value === "passed") return "check";
  if (value === "failed") return "close";
  if (value === "warning") return "alert";
  return "clock";
}

function checkResultVariant(value: string): "success" | "destructive" | "warning" | "outline" {
  if (value === "passed") return "success";
  if (value === "failed") return "destructive";
  if (value === "warning") return "warning";
  return "outline";
}
