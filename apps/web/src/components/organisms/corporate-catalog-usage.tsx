import { DetailAccordion } from "@/components/molecules/detail-accordion";
import type { CorporateCatalogUsage } from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";

const subjectPaths = {
  employee: "employees",
  team: "teams",
  project: "projects",
  technology: "technologies",
} as const;

export function CorporateCatalogUsage({
  items,
  total,
  labels,
}: {
  items: CorporateCatalogUsage[];
  total: number;
  labels: {
    title: string;
    summary: string;
    direct: string;
    effective: string;
    subjectKinds: Record<CorporateCatalogUsage["subject_kind"], string>;
  };
}) {
  if (total === 0) return null;
  return (
    <DetailAccordion
      title={labels.title}
      summary={labels.summary.replace("{count}", String(total))}
    >
      <ul className="divide-border min-w-0 divide-y">
        {items.map((item) => (
          <li key={`${item.subject_kind}:${item.subject_id}:${item.source_team_id ?? "direct"}`}>
            <Link
              href={`/corporate/${subjectPaths[item.subject_kind]}/${encodeURIComponent(item.subject_id)}`}
              className="flex min-w-0 items-start justify-between gap-4 py-3 first:pt-0 last:pb-0"
            >
              <span className="min-w-0">
                <span className="block truncate font-medium">{item.subject_name}</span>
                <span className="text-muted-foreground block text-xs">
                  {labels.subjectKinds[item.subject_kind]}
                </span>
              </span>
              <span className="text-muted-foreground shrink-0 text-xs">
                {item.source === "effective" ? labels.effective : labels.direct}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </DetailAccordion>
  );
}
