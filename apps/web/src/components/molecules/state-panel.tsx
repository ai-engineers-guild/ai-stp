import { cn } from "@/lib/cn";

type StatePanelProps = {
  kind: "loading" | "error" | "empty" | "success";
  title: string;
  description?: string;
  className?: string;
  action?: React.ReactNode;
};

/** Loading / error / empty / success surface for list and detail pages.
 *
 * `kind` is rendered verbatim as the card's eyebrow, so a state the product
 * wants to show needs its own value rather than the nearest spare one: the
 * device-approval page reused `empty` and told a person who had just approved
 * a device "EMPTY".
 */
export function StatePanel({ kind, title, description, className, action }: StatePanelProps) {
  const role = kind === "error" ? "alert" : "status";
  return (
    <div
      role={role}
      aria-live={kind === "loading" ? "polite" : "assertive"}
      data-kind={kind}
      className={cn(
        "rounded-lg border border-border bg-card p-6 text-card-foreground shadow-sm",
        className,
      )}
    >
      <p className="mb-2 font-mono text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
        {kind}
      </p>
      <p className="text-base font-medium">{title}</p>
      {description ? (
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
