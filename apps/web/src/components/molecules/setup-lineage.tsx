import type { SetupVersionPassport } from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";

export function SetupLineage({
  passport,
  labels,
}: {
  passport: Pick<SetupVersionPassport, "ported_from" | "related_setup_ids">;
  labels: { title: string; portedFrom: string; related: string };
}) {
  const source = passport.ported_from;
  if (!source && passport.related_setup_ids.length === 0) return null;
  return (
    <section className="space-y-3 rounded-lg border p-4" aria-label={labels.title}>
      <h2 className="text-lg font-medium">{labels.title}</h2>
      {source ? (
        <div>
          <h3 className="text-sm font-medium">{labels.portedFrom}</h3>
          <Link
            className="break-all underline"
            href={`/catalog/setups/${encodeURIComponent(source.stable_id)}/versions/${encodeURIComponent(source.version)}`}
          >
            {source.stable_id}@{source.version}
          </Link>
        </div>
      ) : null}
      {passport.related_setup_ids.length > 0 ? (
        <div>
          <h3 className="text-sm font-medium">{labels.related}</h3>
          <ul className="space-y-1">
            {passport.related_setup_ids.map((id) => (
              <li key={id}>
                <Link
                  className="break-all underline"
                  href={`/catalog/setups/${encodeURIComponent(id)}`}
                >
                  {id}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
