import { Badge } from "@/components/atoms/badge";
import type { CatalogSupport } from "@/lib/api/generated/types.gen";

export type SupportSummaryLabels = {
  tier: string;
  state: string;
  evidence: string;
  noEvidence: string;
  result: string;
  observedAt: string;
  expiresAt: string;
  noExpiry: string;
};

type SupportSummaryProps = {
  support: CatalogSupport;
  labels: SupportSummaryLabels;
  embedded?: boolean;
};

export function supportLabels(t: (key: string) => string): SupportSummaryLabels {
  return {
    tier: t("supportTier"),
    state: t("supportState"),
    evidence: t("supportEvidence"),
    noEvidence: t("noSupportEvidence"),
    result: t("supportResult"),
    observedAt: t("supportObservedAt"),
    expiresAt: t("supportExpiresAt"),
    noExpiry: t("supportNoExpiry"),
  };
}

export function SupportSummary({ support, labels, embedded = false }: SupportSummaryProps) {
  const evidence = (
    <div className={embedded ? "space-y-2" : undefined}>
      {embedded ? <h3 className="text-sm font-semibold">{labels.evidence}</h3> : null}
      {support.evidence.length === 0 ? (
        <p className="text-sm">{labels.noEvidence}</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {support.evidence.map((item) => (
            <li key={`${item.check_id}-${item.release_reference}`} className="break-words">
              <span className="font-mono">{item.check_id}</span> · {labels.result}: {item.result}
              <span className="text-muted-foreground ml-2">
                {labels.observedAt}: {item.observed_at} · {labels.expiresAt}:{" "}
                {item.expires_at ?? labels.noExpiry}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  if (embedded) return evidence;

  return (
    <div className="space-y-3" aria-labelledby="support-heading">
      <h2 id="support-heading" className="text-xl font-medium tracking-tight">
        {labels.evidence}
      </h2>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">{labels.tier}</dt>
          <dd>
            <Badge variant="outline">{support.tier}</Badge>
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{labels.state}</dt>
          <dd>
            <Badge variant={support.state === "verified" ? "success" : "secondary"}>
              {support.state}
            </Badge>
          </dd>
        </div>
      </dl>
      {evidence}
    </div>
  );
}
