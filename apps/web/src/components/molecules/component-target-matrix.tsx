import { Badge } from "@/components/atoms/badge";
import { CliCopyBlock } from "@/components/molecules/cli-copy-block";
import type { TargetMatrix } from "@/lib/api/generated/types.gen";
import { UI } from "@/lib/ui-selectors";

export type TargetMatrixLabels = {
  heading: string;
  summary: string;
  score: string;
  harness: string;
  availability: string;
  exact: string;
  claimedPortable: string;
  scope: string;
  implementation: string;
  projectionKind: string;
  technicalSupport: string;
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
  transform: string;
  limitations: string;
  validity: string;
  noneListed: string;
  riskInstall: string;
  riskInstallBody: string;
  copyLabel: string;
  copiedLabel: string;
  copyError: string;
  docsLabel: string;
};

export function targetMatrixLabels(
  t: (key: string) => string,
  tCli: (key: string) => string,
): TargetMatrixLabels {
  return {
    heading: t("targetMatrix"),
    summary: t("targetMatrixSummary"),
    score: t("targetMatrixScore"),
    harness: t("harness"),
    availability: t("targetKind"),
    exact: t("exactAvailability"),
    claimedPortable: t("claimedPortable"),
    scope: t("targetScope"),
    implementation: t("implementationMode"),
    projectionKind: t("projectionKind"),
    technicalSupport: t("technicalSupport"),
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
    transform: t("transformFamily"),
    limitations: t("claimLimitations"),
    validity: t("claimValidity"),
    noneListed: t("noneListed"),
    riskInstall: t("riskInstall"),
    riskInstallBody: t("riskInstallBody"),
    copyLabel: tCli("copy"),
    copiedLabel: tCli("copied"),
    copyError: tCli("copyError"),
    docsLabel: tCli("docs"),
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
  if (matrix.exact.length === 0 && matrix.claimed_portable.length === 0) return null;

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
      <MatrixTable matrix={matrix} labels={labels} />
      <MatrixCards matrix={matrix} labels={labels} />
      <RiskCommands matrix={matrix} labels={labels} />
      <div className="sr-only">
        <Badge>{labels.exact}</Badge>
        <Badge>{labels.claimedPortable}</Badge>
        <Badge>{labels.verified}</Badge>
        <Badge>{labels.stale}</Badge>
        <Badge>{labels.failed}</Badge>
        <Badge>{labels.notVerified}</Badge>
        <Badge>{labels.supportSupported}</Badge>
        <Badge>{labels.supportExperimental}</Badge>
        <Badge>{labels.supportUnsupported}</Badge>
      </div>
    </section>
  );
}

function MatrixTable({ matrix, labels }: { matrix: TargetMatrix; labels: TargetMatrixLabels }) {
  return (
    <div className="hidden min-w-0 overflow-x-auto md:block">
      <table className="w-full min-w-[48rem] border-collapse text-left text-sm">
        <caption className="sr-only">{labels.heading}</caption>
        <thead>
          <tr className="border-border border-b">
            <th scope="col" className="py-2 pr-3 font-medium">
              {labels.harness}
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              {labels.availability}
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              {labels.scope}
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              {labels.technicalSupport}
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              {labels.assessment}
            </th>
            <th scope="col" className="py-2 font-medium">
              {labels.recommendation}
            </th>
            <th scope="col" className="py-2 font-medium">
              {labels.projectionKind}
            </th>
          </tr>
        </thead>
        <tbody>
          {matrix.exact.map((row) => (
            <tr
              key={`${row.adaptation_id}:${row.scope}`}
              className="border-border border-b align-top"
            >
              <th scope="row" className="py-3 pr-3 font-medium">
                {row.harness_id}
              </th>
              <td className="py-3 pr-3">{labels.exact}</td>
              <td className="py-3 pr-3">{row.scope}</td>
              <td className="py-3 pr-3">{supportLabel(row.technical_support, labels)}</td>
              <td className="py-3 pr-3">{assessmentLabel(row.assessment_state, labels)}</td>
              <td className="py-3">{recommendationLabel(row.recommendation, labels)}</td>
              <td className="py-3">
                <ProjectionDetails row={row} labels={labels} />
              </td>
            </tr>
          ))}
          {matrix.claimed_portable.map((row) => (
            <tr key={row.claim_id} className="border-border border-b align-top">
              <th scope="row" className="py-3 pr-3 font-medium">
                {row.harness_id}
              </th>
              <td className="py-3 pr-3">{labels.claimedPortable}</td>
              <td className="py-3 pr-3">{row.scopes.join(", ") || labels.noneListed}</td>
              <td className="py-3 pr-3">{labels.noneListed}</td>
              <td className="py-3 pr-3">{labels.notVerified}</td>
              <td className="py-3">{labels.ineffective}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MatrixCards({ matrix, labels }: { matrix: TargetMatrix; labels: TargetMatrixLabels }) {
  return (
    <ul className="space-y-3 md:hidden">
      {matrix.exact.map((row) => (
        <li
          key={`${row.adaptation_id}:${row.scope}`}
          className="border-border space-y-2 rounded-md border p-3"
        >
          <p className="font-medium">{row.harness_id}</p>
          <p className="text-sm">
            {labels.availability}: {labels.exact}
          </p>
          <p className="text-sm">
            {labels.scope}: {row.scope}
          </p>
          <p className="text-sm">
            {labels.implementation}: {row.implementation_mode}
          </p>
          <p className="text-sm">
            {labels.projectionKind}: {row.projection_kind}
          </p>
          <p className="text-sm">
            {labels.technicalSupport}: {supportLabel(row.technical_support, labels)}
          </p>
          <p className="text-sm">
            {labels.assessment}: {assessmentLabel(row.assessment_state, labels)}
          </p>
          <p className="text-sm">
            {labels.recommendation}: {recommendationLabel(row.recommendation, labels)}
          </p>
          <ProjectionDetails row={row} labels={labels} />
        </li>
      ))}
      {matrix.claimed_portable.map((row) => (
        <li key={row.claim_id} className="border-border space-y-2 rounded-md border p-3">
          <p className="font-medium">{row.harness_id}</p>
          <p className="text-sm">
            {labels.availability}: {labels.claimedPortable}
          </p>
          <p className="text-sm">
            {labels.transform}: {row.transform_family} {row.transform_version}
          </p>
          {row.limitations.length ? (
            <p className="text-sm">
              {labels.limitations}: {row.limitations.join(", ")}
            </p>
          ) : null}
          <p className="text-sm">
            {labels.validity}: {row.issued_at}
            {row.expires_at ? ` — ${row.expires_at}` : ""}
          </p>
          {row.risk_cli_command ? (
            <CliCopyBlock
              command={row.risk_cli_command}
              title={labels.riskInstall}
              description={labels.riskInstallBody}
              copyLabel={labels.copyLabel}
              copiedLabel={labels.copiedLabel}
              errorLabel={labels.copyError}
              docsLabel={labels.docsLabel}
              variant="plain"
            />
          ) : null}
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
  return (
    <details className="border-border mt-2 rounded-md border p-2">
      <summary className="cursor-pointer text-sm font-medium underline underline-offset-4">
        {labels.projectionDetails}: {row.harness_id} · {row.projection_kind}
      </summary>
      <dl className="text-muted-foreground mt-3 grid gap-2 text-xs sm:grid-cols-2">
        <div>
          <dt className="text-foreground font-medium">{labels.safetyCheck}</dt>
          <dd>{assessmentLabel(row.assessment_state, labels)}</dd>
        </div>
        <div>
          <dt className="text-foreground font-medium">{labels.recommendation}</dt>
          <dd>{recommendationLabel(row.recommendation, labels)}</dd>
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
            <dt className="text-foreground font-medium">{labels.technicalSupport}</dt>
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
            <dt className="text-foreground font-medium">{labels.scope}</dt>
            <dd>{row.supported_os.join(", ")}</dd>
          </div>
        ) : null}
        {row.supported_arch.length ? (
          <div>
            <dt className="text-foreground font-medium">{labels.scope}</dt>
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
      </dl>
    </details>
  );
}

function RiskCommands({ matrix, labels }: { matrix: TargetMatrix; labels: TargetMatrixLabels }) {
  const commands = matrix.claimed_portable.filter((row) => row.risk_cli_command);
  if (commands.length === 0) return null;
  return (
    <div className="hidden space-y-3 md:block">
      {commands.map((row) => (
        <CliCopyBlock
          key={row.claim_id}
          command={row.risk_cli_command ?? ""}
          title={`${labels.riskInstall} (${row.harness_id})`}
          description={labels.riskInstallBody}
          copyLabel={labels.copyLabel}
          copiedLabel={labels.copiedLabel}
          errorLabel={labels.copyError}
          docsLabel={labels.docsLabel}
        />
      ))}
    </div>
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
