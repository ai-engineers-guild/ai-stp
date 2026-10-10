"use client";

import { useFormatter, useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { ClipboardIconButton } from "@/components/molecules/clipboard-icon-button";
import { CorporateDetailDrawer, PersonIdentity } from "@/components/organisms/corporate-people-ui";
import {
  outcomeVariant,
  targetLabel,
  type AuditEntry,
  type AuditMember,
} from "@/components/organisms/corporate-audit-ui";
import { auditActionLabel } from "@/lib/audit-labels";

export function AuditDrawer({
  item,
  actor,
  onOpenChange,
}: {
  item: AuditEntry | null;
  actor: AuditMember | undefined;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("corporate.auditUi");
  const common = useTranslations("common");
  const formatDate = useFormatter();
  if (!item) return null;
  const hasPayload = Object.keys(item.payload).length > 0;
  const payload = JSON.stringify(item.payload, null, 2);
  const rows: { label: string; value: React.ReactNode }[] = [
    {
      label: t("timestamp"),
      value: (
        <time dateTime={item.created_at}>
          {formatDate.dateTime(new Date(item.created_at), {
            dateStyle: "medium",
            timeStyle: "medium",
          })}
        </time>
      ),
    },
    {
      label: t("actor"),
      value:
        item.actor_type === "user" && actor ? (
          <PersonIdentity
            name={actor.display_name ?? item.actor_account_id ?? ""}
            email={actor.contact_email ?? undefined}
          />
        ) : (
          <span>
            {t(`actors.${item.actor_type}`)}
            {item.actor_id ? (
              <span className="text-muted-foreground mt-0.5 block font-mono text-xs">
                {item.actor_id}
              </span>
            ) : null}
          </span>
        ),
    },
    {
      label: t("action"),
      value: (
        <Badge variant="secondary" className="font-sans font-normal">
          {auditActionLabel(item.action, t)}
        </Badge>
      ),
    },
    {
      label: t("outcome"),
      value: (
        <Badge variant={outcomeVariant(item.outcome)} className="font-sans font-normal">
          {t(`outcomes.${item.outcome}`)}
        </Badge>
      ),
    },
    { label: t("targetType"), value: targetLabel(item.target_table, t) },
    {
      label: t("target"),
      value: <span className="font-mono text-xs break-all">{item.target_id}</span>,
    },
    { label: t("details"), value: item.reason ?? "—" },
  ];
  return (
    <CorporateDetailDrawer
      open
      onOpenChange={onOpenChange}
      title={t("eventDetails")}
      description={auditActionLabel(item.action, t)}
    >
      <dl className="space-y-4">
        {rows.map((row) => (
          <div key={row.label} className="grid grid-cols-[7rem_1fr] gap-3 text-sm">
            <dt className="text-muted-foreground">{row.label}</dt>
            <dd className="min-w-0">{row.value}</dd>
          </div>
        ))}
        {item.request_id ? (
          <div className="grid grid-cols-[7rem_1fr] items-center gap-3 text-sm">
            <dt className="text-muted-foreground">{t("requestId")}</dt>
            <dd className="flex min-w-0 items-center gap-2">
              <code className="min-w-0 truncate font-mono text-xs" title={item.request_id}>
                {item.request_id}
              </code>
              <ClipboardIconButton
                value={item.request_id}
                label={common("copy")}
                copiedLabel={common("copied")}
                errorLabel={common("requestFailed")}
              />
            </dd>
          </div>
        ) : null}
      </dl>
      <div className="mt-6 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-medium">{t("changes")}</h3>
          {hasPayload ? (
            <ClipboardIconButton
              value={payload}
              label={common("copy")}
              copiedLabel={common("copied")}
              errorLabel={common("requestFailed")}
            />
          ) : null}
        </div>
        {hasPayload ? (
          <pre className="border-border bg-muted/30 max-h-96 overflow-auto rounded-md border p-3 font-mono text-xs whitespace-pre-wrap">
            {payload}
          </pre>
        ) : (
          <p className="border-border text-muted-foreground rounded-md border border-dashed p-3 text-sm">
            {t("noChanges")}
          </p>
        )}
      </div>
    </CorporateDetailDrawer>
  );
}
