import { Badge } from "@/components/atoms/badge";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { Link } from "@/lib/i18n/navigation";

export type VersionHistoryEntry = {
  version: string;
  published_at?: string;
  lifecycle: string;
  support: { state: string; tier?: string };
  trust?: { trust_lane: string };
};

export function ObjectVersionHistory({
  title,
  note,
  currentLabel,
  emptyLabel,
  hrefFor,
  versions,
  current,
}: {
  title: string;
  note: string;
  currentLabel: string;
  emptyLabel: string;
  hrefFor: (version: string) => string;
  versions: readonly VersionHistoryEntry[];
  current: string;
}) {
  return (
    <DetailAccordion title={title} summary={note}>
      {versions.length === 0 ? (
        <p className="text-muted-foreground text-sm">{emptyLabel}</p>
      ) : (
        <ol className="border-border relative space-y-0 border-l pl-6">
          {[...versions]
            .sort((left, right) => compareVersions(right.version, left.version))
            .map((entry) => (
              <li key={entry.version} className="relative pb-6 last:pb-0">
                <span className="border-background bg-primary absolute top-1 -left-[1.85rem] h-3 w-3 rounded-full border-2" />
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    href={hrefFor(entry.version)}
                    prefetch={false}
                    className="min-w-0 font-semibold break-all underline underline-offset-4"
                  >
                    {`v${entry.version}`}
                  </Link>
                  {entry.version === current ? <Badge>{currentLabel}</Badge> : null}
                </div>
                <p className="text-muted-foreground mt-1 text-sm">
                  {[
                    entry.published_at,
                    entry.lifecycle,
                    entry.trust?.trust_lane,
                    entry.support.tier,
                    entry.support.state,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </li>
            ))}
        </ol>
      )}
    </DetailAccordion>
  );
}

function compareVersions(left: string, right: string): number {
  const leftParts = left.split(/[.-]/);
  const rightParts = right.split(/[.-]/);
  const length = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = leftParts[index] ?? "0";
    const rightPart = rightParts[index] ?? "0";
    const leftNumber = Number(leftPart);
    const rightNumber = Number(rightPart);
    if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber) && leftNumber !== rightNumber) {
      return leftNumber - rightNumber;
    }
    if (leftPart !== rightPart) return leftPart.localeCompare(rightPart);
  }
  return 0;
}
