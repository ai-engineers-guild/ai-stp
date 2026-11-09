import type { CmdResult } from "../transport";
import { Link } from "react-router";
import { useText } from "../i18n";
import { choiceLabel } from "../labels";
import { record } from "../contexts";

export function Json({ v }: { v: unknown }) {
  return (
    <pre
      // biome-ignore lint/a11y/noNoninteractiveTabindex: The bounded JSON scroll container must be reachable by keyboard.
      tabIndex={0}
      className="max-h-96 overflow-auto rounded-lg bg-muted/50 p-4 font-mono text-xs leading-5 text-foreground"
    >
      {JSON.stringify(v, null, 2)}
    </pre>
  );
}

/** Renders the parts of a CmdResult the caller didn't consume: warnings,
 *  continuations, engine-named next actions, and the structured error. */
export function ResultMeta({ r }: { r: CmdResult }) {
  const t = useText();
  const options = Array.isArray(record(r.error_details).options)
    ? (record(r.error_details).options as unknown[]).filter(
        (o) => typeof o === "string",
      )
    : [];
  const errorBody =
    r.error_code && r.error?.startsWith(`${r.error_code}:`)
      ? r.error.slice(r.error_code.length)
      : r.error;
  return (
    <div className="space-y-2">
      {r.warnings.length > 0 && (
        <div className="card border-warning/50 bg-warning/10 p-3 text-xs">
          {r.warnings.map((w, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: These stateless rows belong to one immutable native reply and may contain duplicate text.
            <p key={i}>⚠ {w}</p>
          ))}
        </div>
      )}
      {r.continuations.length > 0 && (
        <div className="card border-primary/40 bg-primary/5 p-3 text-xs">
          <p className="mb-1 font-semibold">{t("result.nextActions")}</p>
          {r.continuations.map((c, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: These stateless rows belong to one immutable native reply and may contain duplicate text.
            <p key={i}>
              <span className="rounded bg-muted px-1">
                {choiceLabel(t, c.actor ?? "human")}
              </span>{" "}
              {c.path.join(" ")}
              {c.missing.length > 0 &&
                t("result.missingParameters", {
                  parameters: c.missing.join(", "),
                })}
            </p>
          ))}
        </div>
      )}
      {r.next_actions && r.next_actions.length > 0 && (
        <div className="card border-primary/40 bg-primary/5 p-3 text-xs">
          <p className="mb-1 font-semibold">{t("result.theEngineSuggests")}</p>
          {r.next_actions.map((a, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: These stateless rows belong to one immutable native reply and may contain duplicate text.
            <p key={i} className="font-mono">
              {typeof a === "string" ? a : JSON.stringify(a)}
            </p>
          ))}
        </div>
      )}
      {!r.ok && (
        <div
          role="alert"
          className="card border-destructive/50 bg-destructive/10 p-4 text-sm"
        >
          {r.error_code === "IPC_THROW" ? (
            <>
              <p className="font-medium">{t("error.engineConnection")}</p>
              <p className="mt-2">{t("error.uncertainChange")}</p>
              <details className="technical-details mt-3">
                <summary>{t("common.technical")}</summary>
                <code>{r.error_code}</code>
                <p className="break-words">{r.error}</p>
              </details>
            </>
          ) : (
            <>
              <p className="font-medium">{t("error.requestFailed")}</p>
              <details className="technical-details mt-3">
                <summary>{t("error.engineDetails")}</summary>
                {r.error_code && (
                  <code className="font-mono font-semibold">
                    {r.error_code}
                  </code>
                )}
                {r.error_code && errorBody === r.error && " "}
                {errorBody}
              </details>
            </>
          )}
          {r.error_code === "AI_STP_PRECONDITION_FAILED" &&
            record(r.error_details).reason === "historical_native_identity" && (
              <p className="mt-3">
                <Link className="btn-outline" to="/profiles">
                  {t("result.reviewCurrentContext")}
                </Link>
              </p>
            )}
          {options.length > 0 && (
            <p className="mt-1 text-muted-foreground">
              {t("result.options")} {(options as string[]).join(" · ")}
            </p>
          )}
          {r.error_details != null && (
            <details className="mt-1">
              <summary className="cursor-pointer text-muted-foreground">
                {t("result.errorDetails")}
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
  const msg = useText();
  return (
    <div
      role="status"
      className="flex items-center gap-2 text-sm text-muted-foreground"
    >
      <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
      {label ?? msg("result.working")}
    </div>
  );
}

export function Details({ label, value }: { label?: string; value: unknown }) {
  const text = useText();
  return (
    <details className="technical-details">
      <summary>{label ?? text("common.technical")}</summary>
      <Json v={value} />
    </details>
  );
}
