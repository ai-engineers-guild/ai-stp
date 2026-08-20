"use client";

import { useId, useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";
import { Icon } from "@/theme";

export function DetailAccordion({
  title,
  summary,
  headerAction,
  children,
  defaultOpen = false,
  className,
}: {
  title: string;
  summary?: ReactNode;
  headerAction?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const buttonId = useId();
  const panelId = useId();

  return (
    <section className={cn("border-border min-w-0 overflow-hidden rounded-lg border", className)}>
      <div className="flex min-w-0 items-start gap-1">
        <h2 className="min-w-0 flex-1 text-base font-semibold">
          <button
            type="button"
            id={buttonId}
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => {
              setOpen((value) => !value);
            }}
            className="hover:bg-muted/40 focus-visible:bg-muted focus-visible:ring-ring flex min-h-16 w-full cursor-pointer items-center justify-between gap-4 px-4 py-3 text-left focus-visible:ring-2 focus-visible:outline-none sm:px-5"
          >
            <span className="min-w-0 space-y-0.5">
              <span className="block break-words">{title}</span>
              {summary ? (
                <span className="text-muted-foreground block text-sm leading-5 font-normal">
                  {summary}
                </span>
              ) : null}
            </span>
            <Icon name={open ? "chevronUp" : "chevronDown"} size="sm" />
          </button>
        </h2>
        {headerAction ? (
          <div className="flex shrink-0 items-center self-center pr-3">{headerAction}</div>
        ) : null}
      </div>
      {open ? (
        <div
          id={panelId}
          role="region"
          aria-labelledby={buttonId}
          className="border-border border-t px-4 py-4 sm:px-5 sm:py-5"
        >
          {children}
        </div>
      ) : null}
    </section>
  );
}
