"use client";

import { ClipboardIconButton } from "@/components/molecules/clipboard-icon-button";

export function CopyValue({
  value,
  label,
  copied,
  failed,
}: {
  value: string;
  label: string;
  copied: string;
  failed: string;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <code className="min-w-0 truncate text-sm" title={value}>
        {value}
      </code>
      <ClipboardIconButton value={value} label={label} copiedLabel={copied} errorLabel={failed} />
    </div>
  );
}
