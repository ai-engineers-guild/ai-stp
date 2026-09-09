import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";
export type ObjectFilterKind = "all" | "component" | "setup";
export type ScopedObjectFiltersLabels = {
  title: string;
  description: string;
  clear: string;
  apply: string;
  allTypes: string;
  components: string;
  setups: string;
  verifiedOnly: string;
};
export function ScopedObjectFilters({
  kind,
  verifiedOnly = false,
  showVerified = false,
  resetHref,
  labels,
}: {
  kind: ObjectFilterKind;
  verifiedOnly?: boolean;
  showVerified?: boolean;
  resetHref: string;
  labels: ScopedObjectFiltersLabels;
}) {
  const active = [
    ...(kind === "all" ? [] : [kind === "component" ? labels.components : labels.setups]),
    ...(showVerified && verifiedOnly ? [labels.verifiedOnly] : []),
  ];
  return (
    <div className="relative min-w-0 space-y-3">
      <div className="grid min-w-0 items-start gap-4 md:grid-cols-[minmax(0,1fr)_auto]">
        <p className="text-muted-foreground max-w-3xl text-sm leading-relaxed">
          {labels.description}
        </p>
        <details className="group relative md:justify-self-end">
          <summary className="border-border hover:bg-muted focus-visible:ring-ring flex size-11 cursor-pointer list-none items-center justify-center rounded-md border transition-colors focus-visible:ring-2 focus-visible:outline-none">
            <Icon name="controls" size="sm" />
            <span className="sr-only">
              {labels.title}
              {active.length ? ` (${active.length})` : ""}
            </span>
          </summary>
          <form
            className="border-border bg-popover absolute top-[3.25rem] right-0 z-30 w-[min(24rem,calc(100vw-3rem))] space-y-4 rounded-lg border p-4 shadow-md"
            method="get"
          >
            <div className="block space-y-2 text-sm">
              <select
                name="kind"
                defaultValue={kind}
                aria-label={labels.title}
                className="border-input bg-background h-11 w-full rounded-sm border px-3 text-base sm:text-sm"
              >
                <option value="all">{labels.allTypes}</option>
                <option value="component">{labels.components}</option>
                <option value="setup">{labels.setups}</option>
              </select>
            </div>
            {showVerified ? (
              <label className="border-border flex min-h-11 items-center gap-3 rounded-sm border px-3 text-sm">
                <input type="checkbox" name="verified" value="1" defaultChecked={verifiedOnly} />
                <span className="font-medium">{labels.verifiedOnly}</span>
              </label>
            ) : null}
            <div className="border-border flex items-center justify-between gap-3 border-t pt-3">
              <Link
                href={resetHref}
                prefetch={false}
                className="text-muted-foreground inline-flex min-h-11 items-center text-sm underline underline-offset-4"
              >
                {labels.clear}
              </Link>
              <Button type="submit" className="min-h-11">
                <Icon name="filter" size="sm" />
                {labels.apply}
              </Button>
            </div>
          </form>
        </details>
      </div>
      {active.length ? (
        <div className="flex flex-wrap gap-2" aria-label={labels.title}>
          {active.map((value) => (
            <span
              key={value}
              className="border-border bg-muted inline-flex min-h-11 items-center rounded-md border px-3 font-mono text-xs"
            >
              {value}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
