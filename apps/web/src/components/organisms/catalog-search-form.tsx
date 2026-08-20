"use client";

import { useState, useTransition, type FormEvent, type ReactNode } from "react";

import { validateCatalogQuery } from "@/lib/catalog-query";
import { cn } from "@/lib/cn";
import { usePathname, useRouter } from "@/lib/i18n/navigation";

type CatalogSearchFormProps = {
  children: ReactNode;
  className?: string;
  id?: string;
  updatingLabel?: string;
};

/**
 * GET form for catalog filters. Strips empty named fields before submit so
 * empty <select> values never become harness_id= / support_tier= (API 400).
 */
export function CatalogSearchForm({
  children,
  className,
  id,
  updatingLabel = "Updating catalog",
}: CatalogSearchFormProps) {
  const [queryError, setQueryError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const pathname = usePathname();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    const form = event.currentTarget;
    const queryControl = form.elements.namedItem("q");
    if (queryControl instanceof HTMLInputElement) {
      const queryError = validateCatalogQuery(queryControl.value);
      queryControl.setCustomValidity(queryError ?? "");
      queryControl.setAttribute("aria-invalid", queryError ? "true" : "false");
      setQueryError(queryError);
      if (queryError) {
        event.preventDefault();
        queryControl.reportValidity();
        return;
      }
    }
    event.preventDefault();
    const params = new URLSearchParams();
    for (const [key, raw] of new FormData(form).entries()) {
      const value = typeof raw === "string" ? raw.trim() : raw.name.trim();
      if (value) params.append(key, value);
    }
    params.set("page", "1");
    params.delete("cursor");
    params.delete("setups_page");
    params.delete("components_page");
    startTransition(() => {
      router.push(`${pathname}?${params.toString()}`, { scroll: false });
    });
  }

  return (
    <form
      id={id}
      className={cn("min-w-0", className)}
      action=""
      method="get"
      role="search"
      onSubmit={onSubmit}
    >
      {children}
      {pending ? (
        <div
          className="bg-muted mt-3 h-0.5 overflow-hidden"
          role="status"
          aria-label={updatingLabel}
        >
          <div className="bg-primary h-full w-2/5 animate-pulse" />
        </div>
      ) : null}
      {queryError ? (
        <p className="text-destructive mt-2 text-sm" role="alert">
          {queryError}
        </p>
      ) : null}
    </form>
  );
}
