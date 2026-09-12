import { UI } from "@/lib/ui-selectors";

export type ProjectionDockLabels = {
  group: string;
  human: string;
  machine: string;
};

export function ProjectionDockView({
  projection,
  humanHref,
  machineHref,
  labels,
}: {
  projection: "human" | "machine";
  humanHref: string;
  machineHref: string;
  labels: ProjectionDockLabels;
}) {
  const optionStyle = (active: boolean) => ({ opacity: active ? 1 : 0.9 });

  return (
    <aside
      data-ui={UI.projection.toggle}
      data-placement={/\/corporate(?:\/|$)/.test(humanHref) ? "inline" : "fixed"}
      className="projection-dock inline-grid grid-cols-2 gap-2 rounded-sm px-2 py-1"
      aria-label={labels.group}
      style={{
        inlineSize: "16rem",
        width: "16rem",
        gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
      }}
    >
      <a
        data-ui={UI.projection.human}
        href={humanHref}
        aria-current={projection === "human" ? "true" : undefined}
        style={optionStyle(projection === "human")}
        className="projection-dock__option focus-visible:ring-ring inline-flex h-7 min-w-16 items-center justify-center gap-2 rounded-sm px-2 font-mono text-xs font-medium uppercase transition-opacity focus-visible:ring-2 focus-visible:outline-none max-sm:h-11"
      >
        <span
          aria-hidden
          className="projection-dock__dot size-2.5 rounded-full border border-current"
        />
        {labels.human}
      </a>
      <a
        data-ui={UI.projection.machine}
        href={machineHref}
        aria-current={projection === "machine" ? "true" : undefined}
        style={optionStyle(projection === "machine")}
        className="projection-dock__option focus-visible:ring-ring inline-flex h-7 min-w-16 items-center justify-center gap-2 rounded-sm px-2 font-mono text-xs font-medium uppercase transition-opacity focus-visible:ring-2 focus-visible:outline-none max-sm:h-11"
      >
        <span
          aria-hidden
          className="projection-dock__dot size-2.5 rounded-full border border-current"
        />
        {labels.machine}
      </a>
    </aside>
  );
}
