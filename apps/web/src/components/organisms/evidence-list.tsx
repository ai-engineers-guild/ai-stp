import { Badge } from "@/components/atoms/badge";
import type { OwnerEvidenceRow } from "@/lib/api/generated/types.gen";

type EvidenceListProps = {
  items: readonly OwnerEvidenceRow[];
  labels: {
    title: string;
    empty: string;
    check: string;
    result: string;
    source: string;
    expires: string;
  };
};

function resultVariant(
  result: string,
): "default" | "secondary" | "outline" | "success" | "warning" {
  if (result === "passed") {
    return "success";
  }
  if (result === "warning") {
    return "warning";
  }
  if (result === "failed" || result === "expired") {
    return "warning";
  }
  return "outline";
}

/** Compact evidence rows — mono technical meta, semantic chips. */
export function EvidenceList({ items, labels }: EvidenceListProps) {
  if (items.length === 0) {
    return (
      <section className="space-y-2" aria-labelledby="evidence-heading">
        <h2 id="evidence-heading" className="text-lg font-medium tracking-tight">
          {labels.title}
        </h2>
        <p className="text-muted-foreground text-sm">{labels.empty}</p>
      </section>
    );
  }

  return (
    <section className="space-y-3" aria-labelledby="evidence-heading">
      <h2 id="evidence-heading" className="text-lg font-medium tracking-tight">
        {labels.title}
      </h2>
      <ul className="divide-border border-border divide-y rounded-lg border">
        {items.map((item) => (
          <li
            key={`${item.check_id}-${item.source}`}
            className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="min-w-0 space-y-1">
              <p className="text-muted-foreground font-mono text-xs">{labels.check}</p>
              <p className="font-medium">{item.check_id}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={resultVariant(item.result)} className="font-mono text-xs">
                {item.result}
              </Badge>
              <Badge variant="outline" className="font-mono text-xs">
                {item.source}
              </Badge>
              {item.expires_at ? (
                <span className="text-muted-foreground font-mono text-xs">
                  {labels.expires}: {item.expires_at}
                </span>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
