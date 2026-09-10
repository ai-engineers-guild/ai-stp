"use client";

import { useState, useTransition } from "react";

import type { ActiveContext, OrganizationSummary } from "@/lib/api/generated/types.gen";
import { contextStatus, type ProductContextStatus } from "@/lib/product-context";
import { UI } from "@/lib/ui-selectors";

type ProductContextSwitcherProps = {
  context: ActiveContext;
  organizations: readonly OrganizationSummary[];
  status: ProductContextStatus;
  localAvailable: boolean;
  labels: {
    selector: string;
    local: string;
    mode: Record<"personal" | "corporate", string>;
    loading: string;
    failed: string;
    partial: string;
    forbidden: string;
    stale: string;
    unavailable: string;
    unsupported: string;
    empty: string;
    unauthenticated: string;
    switchFailed: string;
  };
};

export function ProductContextSwitcher({
  context,
  organizations,
  status,
  localAvailable,
  labels,
}: ProductContextSwitcherProps) {
  const [pending, startTransition] = useTransition();
  const [failure, setFailure] = useState(false);

  function selectContext(value: string) {
    setFailure(false);
    startTransition(async () => {
      let response: Response;
      try {
        response = await fetch("/api/context/select", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            value === "local"
              ? { mode: "local", organization_id: null }
              : { organization_id: value },
          ),
        });
      } catch {
        setFailure(true);
        return;
      }
      if (!response.ok) {
        setFailure(true);
        return;
      }
      const url = new URL(window.location.href);
      url.searchParams.delete("surface");
      window.location.assign(url.toString());
    });
  }

  const selected = context.mode === "local" ? "local" : (context.organization_id ?? "");
  const viewStatus = contextStatus({ context, organizations: [...organizations], status });
  return (
    <nav
      data-ui={UI.context.switcher}
      aria-label={labels.selector}
      className="border-border bg-background mx-auto flex max-w-6xl items-center gap-2 border-b px-4 py-2 sm:px-6"
    >
      <label htmlFor={UI.context.select} className="text-muted-foreground font-mono text-xs">
        {labels.selector}
      </label>
      <select
        id={UI.context.select}
        data-ui={UI.context.select}
        value={selected}
        disabled={
          pending ||
          viewStatus === "unavailable" ||
          viewStatus === "failed" ||
          viewStatus === "partial" ||
          viewStatus === "forbidden"
        }
        onChange={(event) => {
          selectContext(event.target.value);
        }}
        className="border-border bg-background rounded-md border px-2 py-1 text-sm"
      >
        {localAvailable && <option value="local">{labels.local}</option>}
        {organizations.map((organization) => (
          <option key={organization.organization_id} value={organization.organization_id}>
            {organization.display_name} ({labels.mode[organization.kind]})
          </option>
        ))}
      </select>
      <span className="text-muted-foreground font-mono text-[11px]" aria-live="polite">
        {failure
          ? labels.switchFailed
          : viewStatus === "forbidden"
            ? labels.forbidden
            : viewStatus === "stale"
              ? labels.stale
              : viewStatus === "unavailable"
                ? labels.unavailable
                : viewStatus === "unsupported"
                  ? labels.unsupported
                  : viewStatus === "failed"
                    ? labels.failed
                    : viewStatus === "partial"
                      ? labels.partial
                      : viewStatus === "empty"
                        ? labels.empty
                        : viewStatus === "unauthenticated"
                          ? labels.unauthenticated
                          : pending
                            ? labels.loading
                            : null}
      </span>
    </nav>
  );
}
