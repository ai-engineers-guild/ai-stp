import { Details } from "./Result";
import { StatusBadge } from "./Layout";

export default function TaskOutcome({ value }: { value: unknown }) {
  if (!value || typeof value !== "object")
    return <Details label="Task result" value={value} />;
  const result = value as Record<string, unknown>;
  const fields = [
    ["Harness", result.harness_id],
    ["Setup", result.setup_id],
    ["Setup version", result.setup_version],
    ["Component", result.component_id],
    ["Component version", result.component_version],
    ["Operation", result.operation],
    ["Target roots", result.root_count],
  ].filter(
    ([, value]) => value !== undefined && value !== null && value !== "",
  );
  return (
    <section className="space-y-4 rounded-lg bg-muted/40 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="section-title">
          {typeof result.name === "string" ? result.name : "Task result"}
        </h3>
        {result.verified === true && (
          <StatusBadge state="ready">Installation verified</StatusBadge>
        )}
      </div>
      <dl className="grid gap-3">
        {fields.map(([label, value]) => (
          <div
            key={String(label)}
            className="grid gap-1 sm:grid-cols-[120px_minmax(0,1fr)]"
          >
            <dt className="text-xs text-muted-foreground">{String(label)}</dt>
            <dd className="select-all break-all font-mono text-xs">
              {String(value)}
            </dd>
          </div>
        ))}
      </dl>
      <Details label="Full receipt" value={value} />
    </section>
  );
}
