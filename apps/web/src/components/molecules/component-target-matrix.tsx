import type { SafetyCheckEntry, TargetMatrix } from "@/lib/api/generated/types.gen";
import { UI } from "@/lib/ui-selectors";

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
    safetyCheck: t("safetyCheck"),
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

  return (
    <section
      data-ui={UI.catalog.targetMatrix}
      aria-labelledby="target-matrix-heading"
      className="border-border min-w-0 space-y-4 rounded-lg border p-4"
    >
      <div className="space-y-1">
        <h2 id="target-matrix-heading" className="font-semibold">
          {labels.heading}
        </h2>
        <p className="text-muted-foreground text-sm">{labels.summary}</p>
        <p data-ui={UI.catalog.assurance} className="text-sm">
          {matrixScore(matrix, labels)}
        </p>
      </div>
      <MatrixCards matrix={matrix} labels={labels} />
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
  const safetyChecks =
    (row as unknown as { safety_checks?: SafetyCheckEntry[] }).safety_checks ?? [];

  return (
    <details className="border-border bg-card rounded-lg border shadow-sm">
      <summary className="focus-visible:ring-ring flex min-w-0 cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-2 rounded-lg p-3 focus-visible:ring-2 focus-visible:outline-none [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 flex-1 font-medium break-words">{row.harness_id}</span>
        <span className="text-muted-foreground text-sm">
          {labels.assessment}: {assessmentLabel(row.assessment_state, labels)}
        </span>
        <span className="text-muted-foreground text-sm">
          {labels.implementation}: {row.implementation_mode}
        </span>
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
                    className="border-border flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1 rounded-md border px-2 py-1"
                  >
                    <span className="min-w-0 font-mono break-words">{check.check_id}</span>
                    <span>{checkResultLabel(check.result, labels)}</span>
                    {check.reason ? (
                      <span className="text-muted-foreground basis-full break-words">
                        {check.reason}
                      </span>
                    ) : null}
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

function matrixScore(matrix: TargetMatrix, labels: TargetMatrixLabels): string {
  const assessed = matrix.exact.length;
  const verified = matrix.exact.filter((row) => row.assessment_state === "verified").length;
  const percent = assessed > 0 ? Math.round((verified / assessed) * 100) : 0;
  return `${labels.score}: ${verified} / ${assessed} (${percent}%)`;
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
