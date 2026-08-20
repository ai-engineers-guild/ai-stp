import type { ReactNode } from "react";

import { Badge } from "@/components/atoms/badge";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { SupportSummary, type SupportSummaryLabels } from "@/components/molecules/support-summary";
import type { CatalogSupport, GitSource } from "@/lib/api/generated/types.gen";
import { spdxLicenseUrl } from "@/lib/spdx-license";

export type TechnicalFact = {
  label: string;
  value: ReactNode;
};

export type SourceMetadataLabels = {
  repository: string;
  commit: string;
  path: string;
  empty: string;
};

export function sourceMetadataLabels(t: (key: string) => string): SourceMetadataLabels {
  return {
    repository: t("sourceRepository"),
    commit: t("sourceCommit"),
    path: t("sourcePath"),
    empty: t("noneListed"),
  };
}

export function ObjectTechnicalDetails({
  title,
  summary,
  facts,
  tags,
  licenseId,
  licenseLabel,
  source,
  sourceLabels,
  support,
  supportLabels,
}: {
  title: string;
  summary?: string;
  facts: TechnicalFact[];
  tags?: readonly string[];
  licenseId?: string | null;
  licenseLabel: string;
  source?: GitSource | null;
  sourceLabels?: SourceMetadataLabels;
  support?: CatalogSupport | null;
  supportLabels?: SupportSummaryLabels;
}) {
  const sourceFacts = sourceLabels
    ? [
        { label: sourceLabels.repository, value: source?.repository || sourceLabels.empty },
        { label: sourceLabels.commit, value: source?.commit || sourceLabels.empty },
        { label: sourceLabels.path, value: source?.path || sourceLabels.empty },
      ]
    : [];

  return (
    <DetailAccordion title={title} summary={summary}>
      <div className="space-y-6">
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {facts.map((fact) => (
            <Fact key={fact.label} label={fact.label} value={fact.value} />
          ))}
          {licenseId ? (
            <Fact label={licenseLabel} value={<LicenseValue spdxId={licenseId} />} />
          ) : null}
          {sourceFacts.map((fact) => (
            <Fact
              key={fact.label}
              label={fact.label}
              value={<span className="font-mono text-sm break-all">{fact.value}</span>}
            />
          ))}
          {support && supportLabels ? (
            <>
              <Fact
                label={supportLabels.tier}
                value={<Badge variant="outline">{support.tier}</Badge>}
              />
              <Fact
                label={supportLabels.state}
                value={
                  <Badge variant={support.state === "verified" ? "success" : "secondary"}>
                    {support.state}
                  </Badge>
                }
              />
            </>
          ) : null}
        </dl>
        {tags && tags.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <Badge key={tag} variant="outline">
                {tag}
              </Badge>
            ))}
          </div>
        ) : null}
        {support && supportLabels ? (
          <SupportSummary support={support} labels={supportLabels} embedded />
        ) : null}
      </div>
    </DetailAccordion>
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="bg-muted/30 min-w-0 rounded-sm p-3">
      <dt className="text-muted-foreground text-sm">{label}</dt>
      <dd className="mt-1 font-medium break-words">{value}</dd>
    </div>
  );
}

export function LicenseValue({ spdxId }: { spdxId: string }) {
  const href = spdxLicenseUrl(spdxId);
  if (!href) return <span>{spdxId}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="focus-visible:ring-ring underline underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
    >
      {spdxId}
    </a>
  );
}
