"use client";

import type { ReactNode } from "react";

import { Button } from "@/components/atoms/button";
import { catalogHref } from "@/lib/catalog-query";
import { cn } from "@/lib/cn";
import { Link } from "@/lib/i18n/navigation";
import { pageWindow } from "@/lib/page-window";
import { Icon } from "@/theme";

/**
 * PagePager — the single pagination molecule (link and button modes).
 * Link mode (`hrefFor`) is used by server-rendered listings; button mode
 * (`onPage`) by client-filtered tables. Numbered entries always come from
 * `lib/page-window`; current page carries `aria-current="page"`.
 */
export type PagePagerControls = {
  previous: string;
  next: string;
  page: (value: number) => string;
};

type PagePagerMode =
  | { hrefFor: (page: number) => string; onPage?: never }
  | { onPage: (page: number) => void; hrefFor?: never };

export type PagePagerProps = {
  label: string;
  page: number;
  totalPages: number;
  /** Left side of the bar; defaults to a `page / total` counter. */
  summary?: ReactNode;
  /** Prev/next controls and per-page aria labels; omitted renders numbers only. */
  controls?: PagePagerControls;
  className?: string;
} & PagePagerMode;

const pageLinkClass =
  "border-border aria-[current=page]:bg-primary aria-[current=page]:text-primary-foreground inline-flex h-11 min-w-11 items-center justify-center rounded-sm border px-2 text-xs";

function PagerEntry({
  value,
  current,
  hrefFor,
  onPage,
  ariaLabel,
}: {
  value: number;
  current: boolean;
  hrefFor?: ((page: number) => string) | undefined;
  onPage?: ((page: number) => void) | undefined;
  ariaLabel?: string | undefined;
}) {
  if (hrefFor) {
    return (
      <Link
        href={hrefFor(value)}
        prefetch={false}
        aria-current={current ? "page" : undefined}
        aria-label={ariaLabel}
        className={pageLinkClass}
      >
        {value}
      </Link>
    );
  }
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      aria-current={current ? "page" : undefined}
      aria-label={ariaLabel}
      className={cn("h-11 w-11", current && "border-primary text-primary border")}
      onClick={() => {
        onPage?.(value);
      }}
    >
      {value}
    </Button>
  );
}

function EdgeControl({
  direction,
  disabled,
  hrefFor,
  onPage,
  target,
  ariaLabel,
}: {
  direction: "previous" | "next";
  disabled: boolean;
  hrefFor?: ((page: number) => string) | undefined;
  onPage?: ((page: number) => void) | undefined;
  target: number;
  ariaLabel: string;
}) {
  const icon = <Icon name={direction === "previous" ? "chevronLeft" : "chevronRight"} size="sm" />;
  if (disabled) {
    return (
      <span
        aria-hidden
        className="border-border inline-flex h-11 w-11 items-center justify-center rounded-sm border opacity-50"
      >
        {icon}
      </span>
    );
  }
  if (hrefFor) {
    return (
      <Link
        href={hrefFor(target)}
        prefetch={false}
        aria-label={ariaLabel}
        className="border-border inline-flex h-11 w-11 items-center justify-center rounded-sm border"
      >
        {icon}
      </Link>
    );
  }
  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      aria-label={ariaLabel}
      className="h-11 w-11"
      onClick={() => {
        onPage?.(target);
      }}
    >
      {icon}
    </Button>
  );
}

export function PagePager({
  label,
  page,
  totalPages,
  summary,
  controls,
  className,
  hrefFor,
  onPage,
}: PagePagerProps) {
  return (
    <nav
      aria-label={label}
      className={cn(
        "border-border mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-4",
        className,
      )}
    >
      {summary !== undefined ? (
        summary
      ) : (
        <span className="text-muted-foreground font-mono text-xs">
          {page} / {totalPages}
        </span>
      )}
      <div className="flex max-w-full flex-wrap items-center justify-end gap-1">
        {controls ? (
          <EdgeControl
            direction="previous"
            disabled={page <= 1}
            hrefFor={hrefFor}
            onPage={onPage}
            target={page - 1}
            ariaLabel={controls.previous}
          />
        ) : null}
        {pageWindow(page, totalPages).map((entry, index) =>
          entry === "gap" ? (
            <span
              key={`gap-${index}`}
              className="text-muted-foreground inline-flex h-11 min-w-8 items-center justify-center text-xs"
              aria-hidden="true"
            >
              &hellip;
            </span>
          ) : (
            <PagerEntry
              key={entry}
              value={entry}
              current={entry === page}
              hrefFor={hrefFor}
              onPage={onPage}
              ariaLabel={controls?.page(entry)}
            />
          ),
        )}
        {controls ? (
          <EdgeControl
            direction="next"
            disabled={page >= totalPages}
            hrefFor={hrefFor}
            onPage={onPage}
            target={page + 1}
            ariaLabel={controls.next}
          />
        ) : null}
      </div>
    </nav>
  );
}

/** Cursor listings: an optional "next" deep link above the numbered pager. */
export function SingleResourcePager({
  nextCursor,
  totalPages,
  pageNumber,
  basePath,
  query,
  nextLabel,
  paginationLabel,
}: {
  nextCursor: string | null;
  totalPages: number | null;
  pageNumber: number;
  basePath: string;
  query: Record<string, string>;
  nextLabel: string;
  paginationLabel: string;
}) {
  return (
    <>
      {nextCursor ? (
        <div>
          <Link
            href={catalogHref(basePath, { ...query, cursor: nextCursor })}
            prefetch={false}
            className="text-primary inline-flex min-h-11 items-center text-sm font-medium underline underline-offset-4"
          >
            {nextLabel}
          </Link>
        </div>
      ) : null}
      {totalPages !== null && totalPages > 0 ? (
        <PagePager
          label={paginationLabel}
          page={pageNumber}
          totalPages={totalPages}
          hrefFor={(page) => catalogHref(basePath, { ...query, page: String(page) })}
        />
      ) : null}
    </>
  );
}
