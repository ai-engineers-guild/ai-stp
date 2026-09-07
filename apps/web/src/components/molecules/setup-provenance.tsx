import { Link } from "@/lib/i18n/navigation";

type SetupReference = {
  stable_id: string;
  version: string;
  passport_digest: string;
};

export function SetupProvenance({
  portedFrom,
  relatedSetupIds,
  labels,
}: {
  portedFrom: SetupReference | null;
  relatedSetupIds: string[];
  labels: { heading: string; portedFrom: string; relatedSetups: string };
}) {
  if (!portedFrom && relatedSetupIds.length === 0) return null;

  return (
    <section
      aria-labelledby="setup-provenance-heading"
      className="border-border rounded-lg border p-4"
    >
      <h2 id="setup-provenance-heading" className="font-semibold">
        {labels.heading}
      </h2>
      {portedFrom ? (
        <p className="mt-2">
          <span className="text-muted-foreground mr-2">{labels.portedFrom}</span>
          <Link href={`/catalog/setups/${portedFrom.stable_id}/versions/${portedFrom.version}`}>
            {portedFrom.stable_id}@{portedFrom.version}
          </Link>
        </p>
      ) : null}
      {relatedSetupIds.length > 0 ? (
        <div className="mt-2">
          <p className="text-muted-foreground">{labels.relatedSetups}</p>
          <ul className="mt-1 list-inside list-disc">
            {relatedSetupIds.map((stableId) => (
              <li key={stableId}>
                <Link href={`/catalog/setups/${stableId}`}>{stableId}</Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
