"use client";

import { ClipboardIconButton } from "@/components/molecules/clipboard-icon-button";
import { Link } from "@/lib/i18n/navigation";

type CliCopyBlockProps = {
  command: string;
  title: string;
  description?: string;
  copyLabel: string;
  copiedLabel: string;
  errorLabel: string;
  docsLabel: string;
  docsHref?: string;
  variant?: "card" | "plain";
};

/** Compact install/show CLI panel with copy feedback (SPEC-037 REQ-3706). */
export function CliCopyBlock({
  command,
  title,
  description,
  copyLabel,
  copiedLabel,
  errorLabel,
  docsLabel,
  docsHref = "/docs",
  variant = "card",
}: CliCopyBlockProps) {
  return (
    <section
      className={
        variant === "plain"
          ? "min-w-0 space-y-3"
          : "border-border bg-card min-w-0 space-y-3 rounded-lg border p-3"
      }
    >
      <h2 className="text-sm font-medium tracking-tight">{title}</h2>
      {description ? <p className="text-muted-foreground text-xs">{description}</p> : null}
      <div className="flex min-w-0 items-start gap-2">
        <code className="bg-muted border-border min-w-0 flex-1 rounded-sm border px-2 py-2 font-mono text-xs break-all whitespace-pre-wrap">
          {command}
        </code>
        <ClipboardIconButton
          value={command}
          label={copyLabel}
          copiedLabel={copiedLabel}
          errorLabel={errorLabel}
        />
      </div>
      <p className="text-muted-foreground text-sm">
        <Link href={docsHref} className="underline underline-offset-2">
          {docsLabel}
        </Link>
      </p>
    </section>
  );
}
