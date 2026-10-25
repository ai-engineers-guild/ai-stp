import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import { Building2, UserRound } from "lucide-react";
import { useContexts } from "../contexts";

export default function ContextSwitcher() {
  const { views, selected, loading, switching, result, refresh, select } =
    useContexts();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void refresh();
  }, [refresh, location.pathname]);
  const corporate = selected?.mode === "corporate";
  return (
    <section
      className="mx-3 my-3 space-y-2 rounded-lg border border-border bg-card/60 p-3"
      aria-label="Context view"
    >
      <div className="flex items-center gap-2 text-xs font-medium">
        {corporate ? (
          <Building2 size={15} aria-hidden="true" />
        ) : (
          <UserRound size={15} aria-hidden="true" />
        )}
        <span>{corporate ? "Corporate" : "Personal"} context view</span>
      </div>
      <label className="field-label">
        <span className="sr-only">Selected context view</span>
        <select
          className="input w-full min-w-0 text-xs"
          value={selected?.id ?? ""}
          disabled={loading || switching || !result?.ok}
          onChange={async (event) => {
            setError(null);
            const result = await select(event.target.value);
            if (!result.ok)
              setError(result.error ?? "The context could not be selected.");
          }}
        >
          {!selected && (
            <option value="" disabled>
              {loading
                ? "Reading contexts…"
                : result?.ok
                  ? "Local default"
                  : "Contexts unavailable"}
            </option>
          )}
          {views.map((view) => (
            <option key={view.id} value={view.id}>
              {view.mode === "corporate" ? "Corporate" : "Personal"} ·{" "}
              {view.label}
              {view.origin ? ` · ${view.origin}` : ""}
            </option>
          ))}
        </select>
      </label>
      {selected?.organization && (
        <p className="break-words text-xs text-muted-foreground">
          {selected.organization} · Saved view
        </p>
      )}
      <p className="text-xs leading-5 text-muted-foreground">
        New company reads use this view. Existing tasks keep their original
        context.
      </p>
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
      <Link className="text-xs text-primary hover:underline" to="/profiles">
        Manage contexts
      </Link>
    </section>
  );
}
