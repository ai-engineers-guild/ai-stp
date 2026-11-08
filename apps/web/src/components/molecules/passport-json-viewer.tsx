"use client";

import { ClipboardIconButton } from "@/components/molecules/clipboard-icon-button";
import { highlightedJson } from "@/lib/json-highlight";

export function publicPassportJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function PassportJsonViewer({
  value,
  label,
  copyLabel,
  copiedLabel,
  errorLabel,
}: {
  value: unknown;
  label: string;
  copyLabel: string;
  copiedLabel: string;
  errorLabel?: string;
}) {
  const json = publicPassportJson(value);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{label}</p>
        <ClipboardIconButton
          value={json}
          label={copyLabel}
          copiedLabel={copiedLabel}
          {...(errorLabel ? { errorLabel } : {})}
        />
      </div>
      <pre className="max-h-[32rem] overflow-auto rounded-sm border border-border bg-muted p-3 font-mono text-xs leading-5">
        <code>{highlightedJson(json)}</code>
      </pre>
    </div>
  );
}
