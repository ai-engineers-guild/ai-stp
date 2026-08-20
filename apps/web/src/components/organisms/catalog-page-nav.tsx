import { catalogHref } from "@/lib/catalog-query";
import { pageWindow } from "@/lib/page-window";
import { Link } from "@/lib/i18n/navigation";

export function PageNav({
  label,
  pageNumber,
  totalPages,
  hrefFor,
}: {
  label: string;
  pageNumber: number;
  totalPages: number;
  hrefFor: (page: number) => string;
}) {
  return (
    <nav
      className="border-border mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-4"
      aria-label={label}
    >
      <span className="text-muted-foreground font-mono text-xs">
        {pageNumber} / {totalPages}
      </span>
      <div className="flex flex-wrap gap-1">
        {pageWindow(pageNumber, totalPages).map((entry, index) =>
          entry === "gap" ? (
            <span
              key={`gap-${index}`}
              className="text-muted-foreground inline-flex h-8 min-w-8 items-center justify-center text-xs"
              aria-hidden="true"
            >
              …
            </span>
          ) : (
            <Link
              key={entry}
              href={hrefFor(entry)}
              prefetch={false}
              aria-current={entry === pageNumber ? "page" : undefined}
              className="border-border aria-[current=page]:bg-primary aria-[current=page]:text-primary-foreground inline-flex h-11 min-w-11 items-center justify-center rounded-sm border px-2 text-xs"
            >
              {entry}
            </Link>
          ),
        )}
      </div>
    </nav>
  );
}

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
        <PageNav
          label={paginationLabel}
          pageNumber={pageNumber}
          totalPages={totalPages}
          hrefFor={(page) => catalogHref(basePath, { ...query, page: String(page) })}
        />
      ) : null}
    </>
  );
}
