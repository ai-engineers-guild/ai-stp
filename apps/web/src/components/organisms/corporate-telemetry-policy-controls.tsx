"use client";

import { useRef } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import {
  useGovernanceMutation,
  type GovernanceAuthority,
} from "@/components/organisms/corporate-governance-controls";
import type {
  CorporateTelemetryPolicyRequest,
  CorporateTelemetryPolicyView,
} from "@/lib/api/generated/types.gen";

function TelemetryPolicyFields({
  policy,
  disabled,
}: {
  policy: CorporateTelemetryPolicyView | null;
  disabled: boolean;
}) {
  const t = useTranslations("technology");
  const selectClass =
    "border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2";
  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="telemetry-legal-basis">{t("telemetryLegalBasis")}</Label>
        <select
          id="telemetry-legal-basis"
          name="legal_basis"
          required
          defaultValue={policy?.legal_basis ?? ""}
          className={selectClass}
        >
          <option value="" disabled>
            {t("chooseTelemetryLegalBasis")}
          </option>
          <option value="consent">{t("telemetryBasisConsent")}</option>
          <option value="contract">{t("telemetryBasisContract")}</option>
          <option value="legitimate_interest">{t("telemetryBasisLegitimateInterest")}</option>
        </select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="telemetry-notice">{t("telemetryNotice")}</Label>
        <Textarea
          id="telemetry-notice"
          name="notice_text"
          maxLength={4000}
          defaultValue={policy?.notice_text ?? ""}
          disabled={disabled}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="telemetry-raw-retention">{t("telemetryRawRetention")}</Label>
          <Input
            id="telemetry-raw-retention"
            name="raw_retention_days"
            type="number"
            min={1}
            max={3650}
            required
            defaultValue={policy?.raw_retention_days ?? 90}
            disabled={disabled}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="telemetry-aggregate-retention">{t("telemetryAggregateRetention")}</Label>
          <Input
            id="telemetry-aggregate-retention"
            name="aggregate_retention_days"
            type="number"
            min={1}
            max={3650}
            required
            defaultValue={policy?.aggregate_retention_days ?? 365}
            disabled={disabled}
          />
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor="heartbeat-enabled">{t("heartbeatReporting")}</Label>
        <select
          id="heartbeat-enabled"
          name="heartbeat_enabled"
          defaultValue={String(policy?.heartbeat_enabled ?? true)}
          className={selectClass}
          disabled={disabled}
        >
          <option value="true">{t("heartbeatEnabled")}</option>
          <option value="false">{t("heartbeatDisabled")}</option>
        </select>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="heartbeat-interval">{t("heartbeatIntervalSeconds")}</Label>
          <Input
            id="heartbeat-interval"
            name="heartbeat_interval_seconds"
            type="number"
            min={300}
            max={2592000}
            required
            defaultValue={policy?.heartbeat_interval_seconds ?? 21600}
            disabled={disabled}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="heartbeat-stale">{t("heartbeatStaleSeconds")}</Label>
          <Input
            id="heartbeat-stale"
            name="heartbeat_stale_after_seconds"
            type="number"
            min={60}
            max={31536000}
            required
            defaultValue={policy?.heartbeat_stale_after_seconds ?? 86400}
            disabled={disabled}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="heartbeat-retry-base">{t("heartbeatRetryBaseSeconds")}</Label>
          <Input
            id="heartbeat-retry-base"
            name="heartbeat_retry_base_seconds"
            type="number"
            min={30}
            max={86400}
            required
            defaultValue={policy?.heartbeat_retry_base_seconds ?? 60}
            disabled={disabled}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="heartbeat-retry-max">{t("heartbeatRetryMaxSeconds")}</Label>
          <Input
            id="heartbeat-retry-max"
            name="heartbeat_retry_max_seconds"
            type="number"
            min={60}
            max={604800}
            required
            defaultValue={policy?.heartbeat_retry_max_seconds ?? 3600}
            disabled={disabled}
          />
        </div>
      </div>
    </>
  );
}

// The existing inactivity-policy form does not cover privacy, cadence, or retry fields.
export function CorporateTelemetryPolicyControls({
  policy,
  ...authority
}: GovernanceAuthority & { policy: CorporateTelemetryPolicyView | null }) {
  const t = useTranslations("technology");
  const revision = useRef(policy?.policy_version ?? 0);
  const mutation = useGovernanceMutation(authority);
  return (
    <form
      className="max-w-prose space-y-4"
      aria-busy={mutation.busy}
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const number = (name: string) => {
          const value = data.get(name);
          return typeof value === "string" ? Number(value) : Number.NaN;
        };
        const legalBasis = data.get("legal_basis");
        const enabledValue = data.get("heartbeat_enabled");
        const rawNotice = data.get("notice_text");
        const rawRetention = number("raw_retention_days");
        const aggregateRetention = number("aggregate_retention_days");
        const interval = number("heartbeat_interval_seconds");
        const retryBase = number("heartbeat_retry_base_seconds");
        const retryMax = number("heartbeat_retry_max_seconds");
        const staleAfter = number("heartbeat_stale_after_seconds");
        if (
          typeof legalBasis !== "string" ||
          typeof enabledValue !== "string" ||
          typeof rawNotice !== "string" ||
          ![rawRetention, aggregateRetention, interval, retryBase, retryMax, staleAfter].every(
            Number.isSafeInteger,
          ) ||
          (legalBasis !== "consent" &&
            legalBasis !== "contract" &&
            legalBasis !== "legitimate_interest") ||
          (enabledValue !== "true" && enabledValue !== "false")
        )
          return;
        const noticeText = rawNotice || null;
        const effect = {
          raw_retention_days: rawRetention,
          aggregate_retention_days: aggregateRetention,
          legal_basis: legalBasis,
          notice_text: noticeText,
          notice_revision:
            (policy?.notice_revision ?? 0) + (noticeText !== (policy?.notice_text ?? null) ? 1 : 0),
          heartbeat_enabled: enabledValue === "true",
          heartbeat_interval_seconds: interval,
          heartbeat_retry_base_seconds: retryBase,
          heartbeat_retry_max_seconds: retryMax,
          heartbeat_stale_after_seconds: staleAfter,
          expected_policy_revision: revision.current,
        } satisfies Omit<
          CorporateTelemetryPolicyRequest,
          "schema_version" | "authorization_revision" | "idempotency_key" | "reason"
        >;
        mutation.save(
          `/v1/corporate/organizations/${authority.organizationId}/telemetry/policy`,
          effect,
          "PUT",
          () => {
            revision.current += 1;
          },
        );
      }}
    >
      <div>
        <h2 className="text-xl font-medium">{t("telemetryPolicy")}</h2>
        <p className="text-muted-foreground text-sm">{t("telemetryPolicyDescription")}</p>
      </div>
      <fieldset disabled={mutation.busy} className="space-y-4">
        <TelemetryPolicyFields policy={policy} disabled={mutation.busy} />
      </fieldset>
      <Button type="submit" size="lg" disabled={mutation.busy}>
        {t(mutation.busy ? "saving" : "saveChanges")}
      </Button>
      {mutation.message && <p role="status">{mutation.message}</p>}
    </form>
  );
}
