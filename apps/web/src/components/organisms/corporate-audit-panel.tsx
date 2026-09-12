"use client";

import { useState, useTransition } from "react";

import { corporateAuditExportAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";

import type { CorporateAuditList } from "@/lib/api/generated/types.gen";

type Props = {
  organizationId: string;
  audit: CorporateAuditList;
  labels: {
    title: string;
    export: string;
    exporting: string;
    noAudit: string;
    failed: string;
  };
};

export function CorporateAuditPanel({ organizationId, audit, labels }: Props) {
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);

  function exportAudit() {
    setMessage(null);
    startTransition(async () => {
      const result = await corporateAuditExportAction(organizationId);
      if (!result.ok) {
        setMessage(result.message || labels.failed);
        return;
      }
      const blob = new Blob([JSON.stringify(result.data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${organizationId}-audit.json`;
      link.click();
      URL.revokeObjectURL(url);
    });
  }

  return (
    <section className="border-border bg-card space-y-4 rounded-lg border p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-medium">{labels.title}</h2>
        <Button type="button" disabled={busy} onClick={exportAudit}>
          {busy ? labels.exporting : labels.export}
        </Button>
      </div>
      {audit.items.length ? (
        <ol className="divide-border divide-y text-sm">
          {audit.items.map((item) => (
            <li key={item.audit_id} className="grid gap-1 py-3 sm:grid-cols-[1fr_auto]">
              <span>
                <strong className="font-medium">{item.action}</strong>
                <span className="text-muted-foreground"> · {item.outcome}</span>
              </span>
              <time className="text-muted-foreground" dateTime={item.created_at}>
                {item.created_at}
              </time>
              <span className="text-muted-foreground truncate sm:col-span-2">
                {item.target_table}:{item.target_id}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-muted-foreground text-sm">{labels.noAudit}</p>
      )}
      {message ? (
        <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
          {message}
        </p>
      ) : null}
    </section>
  );
}
