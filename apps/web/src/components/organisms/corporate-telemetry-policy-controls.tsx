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

const selectClass =
  "border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2";

type BooleanFieldDef = {
  id: string;
  name:
    | "heartbeat_enabled"
    | "inventory_scan_enabled"
    | "usage_collection_enabled"
    | "usage_registration_required";
  labelKey:
    | "heartbeatReporting"
    | "inventoryScanReporting"
    | "usageCollectionReporting"
    | "usageRegistrationRequired";
  fallback: boolean;
};

const BOOLEAN_FIELDS_SINGLE: readonly BooleanFieldDef[] = [
  {
    id: "heartbeat-enabled",
    name: "heartbeat_enabled",
    labelKey: "heartbeatReporting",
    fallback: true,
  },
  {
    id: "inventory-scan-enabled",
    name: "inventory_scan_enabled",
    labelKey: "inventoryScanReporting",
    fallback: false,
  },
];

const BOOLEAN_FIELDS_GRID: readonly BooleanFieldDef[] = [
  {
    id: "usage-collection-enabled",
    name: "usage_collection_enabled",
    labelKey: "usageCollectionReporting",
    fallback: false,
  },
  {
    id: "usage-registration-required",
    name: "usage_registration_required",
    labelKey: "usageRegistrationRequired",
    fallback: false,
  },
];

const CADENCE_FIELDS = [
  {
    id: "heartbeat-interval",
    name: "heartbeat_interval_seconds",
    labelKey: "heartbeatIntervalSeconds",
    min: 60,
    max: 2592000,
    fallback: 21600,
  },
  {
    id: "heartbeat-stale",
    name: "heartbeat_stale_after_seconds",
    labelKey: "heartbeatStaleSeconds",
    min: 60,
    max: 31536000,
    fallback: 86400,
  },
  {
    id: "heartbeat-retry-base",
    name: "heartbeat_retry_base_seconds",
    labelKey: "heartbeatRetryBaseSeconds",
    min: 30,
    max: 86400,
    fallback: 60,
  },
  {
    id: "heartbeat-retry-max",
    name: "heartbeat_retry_max_seconds",
    labelKey: "heartbeatRetryMaxSeconds",
    min: 60,
    max: 604800,
    fallback: 3600,
  },
] as const;

function BooleanSelectField({
  id,
  name,
  label,
  value,
  disabled,
  t,
}: {
  id: string;
  name: string;
  label: string;
  value: boolean;
  disabled: boolean;
  t: (key: string) => string;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        name={name}
        defaultValue={String(value)}
        className={selectClass}
        disabled={disabled}
      >
        <option value="true">{t("heartbeatEnabled")}</option>
        <option value="false">{t("heartbeatDisabled")}</option>
      </select>
    </div>
  );
}

function TelemetryPolicyFields({
  policy,
  disabled,
}: {
  policy: CorporateTelemetryPolicyView | null;
  disabled: boolean;
}) {
  const t = useTranslations("technology");
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
      {BOOLEAN_FIELDS_SINGLE.map((field) => (
        <BooleanSelectField
          key={field.name}
          id={field.id}
          name={field.name}
          label={t(field.labelKey)}
          value={policy?.[field.name] ?? field.fallback}
          disabled={disabled}
          t={t}
        />
      ))}
      <div className="grid gap-4 sm:grid-cols-2">
        {BOOLEAN_FIELDS_GRID.map((field) => (
          <BooleanSelectField
            key={field.name}
            id={field.id}
            name={field.name}
            label={t(field.labelKey)}
            value={policy?.[field.name] ?? field.fallback}
            disabled={disabled}
            t={t}
          />
        ))}
      </div>
      <div className="space-y-2">
        <Label htmlFor="report-timezone">{t("reportTimezone")}</Label>
        <Input
          id="report-timezone"
          name="report_timezone"
          required
          maxLength={64}
          defaultValue={policy?.report_timezone ?? "UTC"}
          disabled={disabled}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {CADENCE_FIELDS.map((field) => (
          <div key={field.name} className="space-y-2">
            <Label htmlFor={field.id}>{t(field.labelKey)}</Label>
            <Input
              id={field.id}
              name={field.name}
              type="number"
              min={field.min}
              max={field.max}
              required
              defaultValue={policy?.[field.name] ?? field.fallback}
              disabled={disabled}
            />
          </div>
        ))}
      </div>
    </>
  );
}

type ParsedTelemetryForm = {
  rawRetention: number;
  aggregateRetention: number;
  legalBasis: "consent" | "contract" | "legitimate_interest";
  noticeText: string | null;
  heartbeatEnabled: boolean;
  inventoryScanEnabled: boolean;
  usageCollectionEnabled: boolean;
  usageRegistrationRequired: boolean;
  reportTimezone: string;
  interval: number;
  retryBase: number;
  retryMax: number;
  staleAfter: number;
};

function parseTelemetryForm(data: FormData): ParsedTelemetryForm | null {
  const number = (name: string) => {
    const value = data.get(name);
    return typeof value === "string" ? Number(value) : Number.NaN;
  };
  const legalBasis = data.get("legal_basis");
  const rawNotice = data.get("notice_text");
  const reportTimezone = data.get("report_timezone");
  const parseBool = (key: string): boolean | null => {
    const val = data.get(key);
    return val === "true" ? true : val === "false" ? false : null;
  };

  const heartbeatEnabled = parseBool("heartbeat_enabled");
  const inventoryScanEnabled = parseBool("inventory_scan_enabled");
  const usageCollectionEnabled = parseBool("usage_collection_enabled");
  const usageRegistrationRequired = parseBool("usage_registration_required");

  if (
    typeof legalBasis !== "string" ||
    (legalBasis !== "consent" &&
      legalBasis !== "contract" &&
      legalBasis !== "legitimate_interest") ||
    typeof rawNotice !== "string" ||
    typeof reportTimezone !== "string" ||
    !reportTimezone ||
    heartbeatEnabled === null ||
    inventoryScanEnabled === null ||
    usageCollectionEnabled === null ||
    usageRegistrationRequired === null ||
    (usageRegistrationRequired && !usageCollectionEnabled)
  ) {
    return null;
  }

  const rawRetention = number("raw_retention_days");
  const aggregateRetention = number("aggregate_retention_days");
  const interval = number("heartbeat_interval_seconds");
  const retryBase = number("heartbeat_retry_base_seconds");
  const retryMax = number("heartbeat_retry_max_seconds");
  const staleAfter = number("heartbeat_stale_after_seconds");

  if (
    ![rawRetention, aggregateRetention, interval, retryBase, retryMax, staleAfter].every(
      Number.isSafeInteger,
    )
  ) {
    return null;
  }

  return {
    rawRetention,
    aggregateRetention,
    legalBasis,
    noticeText: rawNotice || null,
    heartbeatEnabled,
    inventoryScanEnabled,
    usageCollectionEnabled,
    usageRegistrationRequired,
    reportTimezone,
    interval,
    retryBase,
    retryMax,
    staleAfter,
  };
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
        const parsed = parseTelemetryForm(new FormData(event.currentTarget));
        if (!parsed) return;
        const effect = {
          raw_retention_days: parsed.rawRetention,
          aggregate_retention_days: parsed.aggregateRetention,
          legal_basis: parsed.legalBasis,
          notice_text: parsed.noticeText,
          notice_revision:
            (policy?.notice_revision ?? 0) +
            (parsed.noticeText !== (policy?.notice_text ?? null) ? 1 : 0),
          heartbeat_enabled: parsed.heartbeatEnabled,
          inventory_scan_enabled: parsed.inventoryScanEnabled,
          usage_collection_enabled: parsed.usageCollectionEnabled,
          usage_registration_required: parsed.usageRegistrationRequired,
          report_timezone: parsed.reportTimezone,
          heartbeat_interval_seconds: parsed.interval,
          heartbeat_retry_base_seconds: parsed.retryBase,
          heartbeat_retry_max_seconds: parsed.retryMax,
          heartbeat_stale_after_seconds: parsed.staleAfter,
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
