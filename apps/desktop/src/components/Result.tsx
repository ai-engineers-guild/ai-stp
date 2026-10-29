import type { CmdResult } from "../transport";
import { Link } from "react-router";

export function Json({ v }: { v: unknown }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-lg bg-muted/50 p-4 font-mono text-xs leading-5 text-foreground">
      {JSON.stringify(v, null, 2)}
    </pre>
  );
}

/** Renders the parts of a CmdResult the caller didn't consume: warnings,
 *  continuations, engine-named next actions, and the structured error. */
export function ResultMeta({ r }: { r: CmdResult }) {
  const options = Array.isArray(r.error_details?.options)
    ? (r.error_details?.options as unknown[]).filter(
        (o) => typeof o === "string",
      )
    : [];
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
              <span className="rounded bg-muted px-1">
                {c.actor ?? "human"}
              </span>{" "}
              {c.path.join(" ")}
              {c.missing.length > 0 && ` — needs: ${c.missing.join(", ")}`}
            </p>
          ))}
        </div>
      )}
      {r.next_actions && r.next_actions.length > 0 && (
        <div className="card border-primary/40 bg-primary/5 p-3 text-xs">
          <p className="mb-1 font-semibold">The engine suggests</p>
          {r.next_actions.map((a, i) => (
            <p key={i} className="font-mono">
              {typeof a === "string" ? a : JSON.stringify(a)}
            </p>
          ))}
        </div>
      )}
      {r.error && (
        <div
          role="alert"
          className="card border-destructive/50 bg-destructive/10 p-4 text-sm"
        >
          {r.error_code && !r.error.startsWith(`${r.error_code}:`) && (
            <span className="mr-2 font-mono font-semibold">{r.error_code}</span>
          )}
          {r.error}
          {r.error_code === "AI_STP_PRECONDITION_FAILED" &&
            r.error_details?.reason === "historical_native_identity" && (
              <p className="mt-3">
                <Link className="btn-outline" to="/profiles">Review current context</Link>
              </p>
            )}
          {options.length > 0 && (
            <p className="mt-1 text-muted-foreground">
              options: {(options as string[]).join(" · ")}
            </p>
          )}
          {r.error_details != null && (
            <details className="mt-1">
              <summary className="cursor-pointer text-muted-foreground">
                error details
              </summary>
              <Json v={r.error_details} />
            </details>
          )}
        </div>
      )}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div
      role="status"
      className="flex items-center gap-2 text-sm text-muted-foreground"
    >
      <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
      {label ?? "Working…"}
    </div>
  );
}

export function Details({
  label = "Technical details",
  value,
}: {
  label?: string;
  value: unknown;
}) {
  return (
    <details className="technical-details">
      <summary>{label}</summary>
      <Json v={value} />
    </details>
  );
}
