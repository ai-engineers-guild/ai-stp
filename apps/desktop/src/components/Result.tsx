import type { CmdResult } from "../transport";

export function Json({ v }: { v: unknown }) {
  return (
    <pre className="overflow-auto rounded-lg bg-muted/50 p-3 text-xs leading-5 text-foreground dark:bg-muted/50">
      {JSON.stringify(v, null, 2)}
    </pre>
  );
}

/** Renders the parts of a CmdResult the caller didn't consume: warnings,
 *  continuations and the structured error. */
export function ResultMeta({ r }: { r: CmdResult }) {
  return (
    <div className="space-y-2">
      {r.warnings.length > 0 && (
        <div className="card border-warning/50 bg-warning/10 p-3 text-xs">
          {r.warnings.map((w, i) => (
            <p key={i}>⚠ {w}</p>
          ))}
        </div>
      )}
      {r.continuations.length > 0 && (
        <div className="card border-primary/40 bg-primary/5 p-3 text-xs">
          <p className="mb-1 font-semibold">Next actions</p>
          {r.continuations.map((c, i) => (
            <p key={i}>
              <span className="rounded bg-sky-600/20 px-1">{c.actor ?? "cli"}</span>{" "}
              {c.path.join(" ")}
              {c.missing.length > 0 && ` — needs: ${c.missing.join(", ")}`}
            </p>
          ))}
        </div>
      )}
      {r.error && (
        <div className="card border-destructive/50 bg-destructive/10 p-3 text-xs">
          {r.error_code && !r.error.startsWith(`${r.error_code}:`) && (
            <span className="mr-2 font-mono font-semibold">{r.error_code}</span>
          )}
          {r.error}
        </div>
      )}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
      {label ?? "Working…"}
    </div>
  );
}
