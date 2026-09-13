"use client";

import { useState, useTransition } from "react";
import { useFormatter, useTranslations } from "next-intl";

import { corporateAuditExportAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";

import type { CorporateAuditList } from "@/lib/api/generated/types.gen";

type Props = {
  organizationId: string;
  audit: CorporateAuditList;
  members?: readonly { account_id: string; display_name: string | null }[];
  labels: {
    title: string;
    export: string;
    exporting: string;
    noAudit: string;
    failed: string;
  };
};

export function CorporateAuditPanel({ organizationId, audit, labels, members = [] }: Props) {
  const t = useTranslations("corporate.auditUi");
  const format = useFormatter();
  const actors = new Map(
    members
      .filter((member) => member.display_name)
      .map((member) => [member.account_id, member.display_name]),
  );
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);

  function exportAudit() {
    setMessage(null);
    startTransition(async () => {
      try {
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
      } catch {
        setMessage(labels.failed);
      }
    });
  }

  return (
    <section className="space-y-4">
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
                <strong className="font-medium">{auditActionLabel(item.action, t)}</strong>
                <span className="text-muted-foreground">
                  {" "}
                  ·{" "}
                  {item.outcome === "succeeded"
                    ? t("outcomes.succeeded")
                    : item.outcome === "denied"
                      ? t("outcomes.denied")
                      : t("outcomes.failed")}
                </span>
              </span>
              <time className="text-muted-foreground" dateTime={item.created_at}>
                {format.dateTime(new Date(item.created_at), {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}
              </time>
              <span className="text-muted-foreground sm:col-span-2">
                {item.actor_type === "user" &&
                item.actor_account_id &&
                actors.has(item.actor_account_id) ? (
                  <Link
                    href={`/corporate/members/${item.actor_account_id}`}
                    className="underline underline-offset-4"
                  >
                    {actors.get(item.actor_account_id)}
                  </Link>
                ) : (
                  t(`actors.${item.actor_type}`)
                )}
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

function auditActionLabel(action: string, t: ReturnType<typeof useTranslations>) {
  const parts = action.split(".");
  const entity = parts[0] ?? "";
  const operation = parts.at(-1) ?? "";
  if (action === "member.profile.update") return t("profileUpdated");
  if (
    ![
      "member",
      "team",
      "project",
      "role",
      "binding",
      "service_principal",
      "catalog_assignment",
      "audit",
      "organization",
      "corporate",
    ].includes(entity)
  )
    return t("otherEvent");
  if (
    ![
      "create",
      "update",
      "delete",
      "read",
      "list",
      "write",
      "export",
      "lifecycle",
      "bootstrap",
      "replay",
    ].includes(operation)
  )
    return t("otherEvent");
  return t("event", { entity: t(`entities.${entity}`), operation: t(`operations.${operation}`) });
}
