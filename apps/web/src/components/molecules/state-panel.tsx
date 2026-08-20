import { cn } from "@/lib/cn";

type StatePanelProps = {
  kind: "loading" | "error" | "empty";
  title: string;
  description?: string;
  className?: string;
  action?: React.ReactNode;
};

/** Empty / loading / error surface for list and detail pages. */
export function StatePanel({ kind, title, description, className, action }: StatePanelProps) {
  const role = kind === "error" ? "alert" : "status";
  return (
    <div
      role={role}
      aria-live={kind === "loading" ? "polite" : "assertive"}
      data-kind={kind}
      className={cn(
        "border-border bg-card text-card-foreground rounded-lg border p-6 shadow-sm",
        className,
      )}
    >
      <p className="text-muted-foreground mb-2 font-mono text-[11px] font-medium tracking-wide uppercase">
        {kind}
      </p>
      <p className="text-base font-medium">{title}</p>
      {description ? (
        <p className="text-muted-foreground mt-2 text-sm leading-relaxed">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
