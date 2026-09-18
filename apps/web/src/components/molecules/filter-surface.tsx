"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { Button } from "@/components/atoms/button";
import { cn } from "@/lib/cn";
import { Icon } from "@/theme";

const REFINE_FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

function refineFocusables(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(REFINE_FOCUSABLE)].filter(
    (el) => el.getAttribute("aria-hidden") !== "true" && el.tabIndex !== -1,
  );
}

export function RefineSurface({
  labels,
  onClose,
  children,
  id = "catalog-refine",
}: {
  labels: { refineButton?: string | undefined; filtersButton: string; closeFilters: string };
  onClose: () => void;
  children: ReactNode;
  id?: string;
}) {
  const title = labels.refineButton ?? labels.filtersButton;
  const surfaceRef = useRef<HTMLElement>(null);
  // Assigned after commit, not during render. A render React throws away
  // would otherwise leave this pointing at a handler that never took effect.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const first = refineFocusables(surface)[0];
    (first ?? surface).focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = refineFocusables(surface);
      if (items.length === 0) return;
      const start = items[0];
      const end = items[items.length - 1];
      if (!start || !end) return;
      if (event.shiftKey && document.activeElement === start) {
        event.preventDefault();
        end.focus();
      } else if (!event.shiftKey && document.activeElement === end) {
        event.preventDefault();
        start.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", onKeyDown);
      previous?.focus();
    };
  }, []);

  return (
    <>
      <button
        type="button"
        className="bg-foreground/40 fixed inset-0 z-[60]"
        aria-label={labels.closeFilters}
        tabIndex={-1}
        onClick={onClose}
      />
      <section
        ref={surfaceRef}
        id={id}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        tabIndex={-1}
        data-filter-surface="drawer"
        className={cn(
          "border-border bg-card fixed z-[70] overflow-x-hidden overflow-y-auto border shadow-md",
          "inset-x-0 bottom-0 max-h-[min(92dvh,calc(100vh-1rem))] w-full rounded-t-lg px-4",
          "pb-[max(1.25rem,env(safe-area-inset-bottom))]",
          "md:inset-auto md:top-1/2 md:left-1/2 md:max-h-[calc(100vh-2rem)] md:w-[calc(100vw-2rem)]",
          "md:max-w-3xl md:-translate-x-1/2 md:-translate-y-1/2 md:rounded-lg md:px-6",
        )}
      >
        <div className="border-border bg-card sticky top-0 z-10 mb-5 flex min-w-0 items-center justify-between gap-3 border-b py-4 sm:py-5">
          <h2 id={`${id}-title`} className="min-w-0 text-lg font-medium break-words">
            {title}
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-11 w-11 shrink-0"
            aria-label={labels.closeFilters}
            onClick={onClose}
          >
            <Icon name="close" size="sm" />
          </Button>
        </div>
        {children}
      </section>
    </>
  );
}
