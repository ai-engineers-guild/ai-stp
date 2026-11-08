import type { ReactNode } from "react";
import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";

export function CorporateReportCard({
  title,
  description,
  href,
  openLabel,
  preview,
}: {
  title: string;
  description: string;
  href: string;
  openLabel: string;
  preview: ReactNode;
}) {
  return (
    <article className="grid min-h-56 gap-5 rounded-lg border border-border bg-card p-5 transition-colors hover:border-foreground/40 md:grid-cols-2">
      <div
        aria-hidden="true"
        className="overflow-hidden rounded-sm border border-border bg-background p-3 text-xs"
      >
        {preview}
      </div>
      <div className="flex min-w-0 flex-col">
        <h2 className="text-lg font-medium">{title}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{description}</p>
        <div className="mt-auto border-t border-border pt-4">
          <Button asChild size="sm">
            <Link href={href}>{openLabel} →</Link>
          </Button>
        </div>
      </div>
    </article>
  );
}
