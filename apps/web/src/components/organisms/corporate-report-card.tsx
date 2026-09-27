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
    <article className="border-border bg-card hover:border-foreground/40 grid min-h-56 gap-5 rounded-lg border p-5 transition-colors md:grid-cols-2">
      <div
        aria-hidden="true"
        className="border-border bg-background overflow-hidden rounded-sm border p-3 text-xs"
      >
        {preview}
      </div>
      <div className="flex min-w-0 flex-col">
        <h2 className="text-lg font-medium">{title}</h2>
        <p className="text-muted-foreground mt-2 text-sm">{description}</p>
        <div className="border-border mt-auto border-t pt-4">
          <Button asChild size="sm">
            <Link href={href}>{openLabel} →</Link>
          </Button>
        </div>
      </div>
    </article>
  );
}
