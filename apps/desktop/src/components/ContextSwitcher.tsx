import { iconSize } from "../generated/theme";
import { useText } from "../i18n";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import { Building2, UserRound } from "lucide-react";
import { useContexts } from "../contexts";
import type { CmdResult } from "../transport";
import { ResultMeta } from "./Result";

export default function ContextSwitcher() {
  const msg = useText();
  const { views, selected, loading, switching, result, refresh, select } =
    useContexts();
  const location = useLocation();
  const [error, setError] = useState<CmdResult | null>(null);
  useEffect(() => {
    void refresh();
  }, [refresh, location.pathname]);
  const corporate = selected?.mode === "corporate";
  return (
    <section
      className="mx-3 my-3 shrink-0 space-y-2 rounded-lg border border-border bg-card/60 p-3"
      aria-label={msg("contextSwitcher.contextView")}
    >
      <div className="flex items-center gap-2 text-xs font-medium">
        {corporate ? (
          <Building2 style={iconSize.sm} aria-hidden="true" />
        ) : (
          <UserRound style={iconSize.sm} aria-hidden="true" />
        )}
        <span>
          {msg("contextSwitcher.modeTitle", {
            mode: corporate ? "corporate" : "personal",
          })}
        </span>
      </div>
      <label className="field-label">
        <span className="sr-only">
          {msg("contextSwitcher.selectedContextView")}
        </span>
        <select
          className="input w-full min-w-0 text-xs"
          value={selected?.id ?? ""}
          disabled={loading || switching || !result?.ok}
          onChange={async (event) => {
            setError(null);
            const result = await select(event.target.value);
            if (!result.ok) setError(result);
          }}
        >
          {!selected && (
            <option value="" disabled>
              {loading
                ? msg("contextSwitcher.readingContexts")
                : result?.ok
                  ? msg("contextSwitcher.localDefault")
                  : msg("contextSwitcher.contextsUnavailable")}
            </option>
          )}
          {views.map((view) => (
            <option key={view.id} value={view.id}>
              {view.mode === "corporate"
                ? msg("contextSwitcher.corporate")
                : msg("contextSwitcher.personal")}{" "}
              · {view.label}
              {view.origin ? ` · ${view.origin}` : ""}
            </option>
          ))}
        </select>
      </label>
      {selected?.organization && (
        <p className="break-words text-xs text-muted-foreground">
          {selected.organization} {msg("contextSwitcher.savedView")}
        </p>
      )}
      <p className="text-xs leading-5 text-muted-foreground">
        {msg("contextSwitcher.newCompanyReadsUseThisViewExistingTasksKeep")}
      </p>
      {error && <ResultMeta r={error} />}
      <Link className="text-xs text-primary hover:underline" to="/profiles">
        {msg("contextSwitcher.manageContexts")}
      </Link>
    </section>
  );
}
