"use client";

import { useRef } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import {
  useGovernanceMutation,
  type GovernanceAuthority,
} from "@/components/organisms/corporate-governance-controls";
import {
  AdvancedDisclosure,
  PresetCadenceField,
  PrivacyReportingSection,
  SwitchRow,
  UnitSecondsField,
} from "@/components/organisms/corporate-telemetry-policy-fields";
import type {
  CorporateTelemetryPolicyRequest,
  CorporateTelemetryPolicyView,
} from "@/lib/api/generated/types.gen";

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
  hintKey?:
    "heartbeatEnabledHint" | "inventoryScanHint" | "usageCollectionHint" | "usageRegistrationHint";
  fallback: boolean;
};

const HEARTBEAT_TOGGLE: BooleanFieldDef = {
  id: "heartbeat-enabled",
  name: "heartbeat_enabled",
  labelKey: "heartbeatReporting",
  hintKey: "heartbeatEnabledHint",
  fallback: true,
};

const INVENTORY_TOGGLE: BooleanFieldDef = {
  id: "inventory-scan-enabled",
  name: "inventory_scan_enabled",
  labelKey: "inventoryScanReporting",
  hintKey: "inventoryScanHint",
  fallback: false,
};

const USAGE_TOGGLES: readonly BooleanFieldDef[] = [
  {
    id: "usage-collection-enabled",
    name: "usage_collection_enabled",
    labelKey: "usageCollectionReporting",
    hintKey: "usageCollectionHint",
    fallback: false,
  },
  {
    id: "usage-registration-required",
    name: "usage_registration_required",
    labelKey: "usageRegistrationRequired",
    hintKey: "usageRegistrationHint",
    fallback: false,
  },
];

// Presets are display conveniences; the submitted value stays in seconds.
const HEARTBEAT_INTERVAL_PRESETS = [60, 300, 900, 3600, 21600, 86400] as const;
const HEARTBEAT_STALE_PRESETS = [3600, 21600, 86400, 259200, 604800] as const;

function TelemetryPolicyFields({
  policy,
  disabled,
}: {
  policy: CorporateTelemetryPolicyView | null;
  disabled: boolean;
}) {
  const t = useTranslations("technology");
  const toggle = (field: BooleanFieldDef) => (
    <SwitchRow
      key={field.name}
      id={field.id}
      name={field.name}
      label={t(field.labelKey)}
      hint={field.hintKey ? t(field.hintKey) : undefined}
      value={policy?.[field.name] ?? field.fallback}
      disabled={disabled}
    />
  );
  return (
    <>
      <section className="border-border space-y-4 border-t pt-4">
        <h3 className="text-sm font-medium">{t("sectionDeviceHeartbeat")}</h3>
        {toggle(HEARTBEAT_TOGGLE)}
        <div className="grid gap-4 sm:grid-cols-2">
          <PresetCadenceField
            id="heartbeat-interval"
            name="heartbeat_interval_seconds"
            label={t("heartbeatInterval")}
            hint={t("heartbeatIntervalHint")}
            presets={HEARTBEAT_INTERVAL_PRESETS}
            seconds={policy?.heartbeat_interval_seconds ?? 21600}
            customUnit={60}
            customLabelKey="customIntervalMinutes"
            customMin={1}
            customMax={43200}
            disabled={disabled}
            t={t}
          />
          <PresetCadenceField
            id="heartbeat-stale"
            name="heartbeat_stale_after_seconds"
            label={t("heartbeatStale")}
            hint={t("heartbeatStaleHint")}
            presets={HEARTBEAT_STALE_PRESETS}
            seconds={policy?.heartbeat_stale_after_seconds ?? 86400}
            customUnit={3600}
            customLabelKey="customStaleHours"
            customMin={1}
            customMax={8760}
            disabled={disabled}
            t={t}
          />
        </div>
        <AdvancedDisclosure title={t("advanced")}>
          <div className="grid gap-4 sm:grid-cols-2">
            <UnitSecondsField
              id="heartbeat-retry-base"
              name="heartbeat_retry_base_seconds"
              label={t("heartbeatRetryBaseSeconds")}
              hint={t("heartbeatRetryBaseHint")}
              seconds={policy?.heartbeat_retry_base_seconds ?? 60}
              unit={1}
              min={30}
              max={86400}
              disabled={disabled}
            />
            <UnitSecondsField
              id="heartbeat-retry-max"
              name="heartbeat_retry_max_seconds"
              label={t("heartbeatRetryMaxMinutes")}
              hint={t("heartbeatRetryMaxHint")}
              seconds={policy?.heartbeat_retry_max_seconds ?? 3600}
              unit={60}
              min={1}
              max={10080}
              disabled={disabled}
            />
          </div>
        </AdvancedDisclosure>
      </section>
      <section className="border-border space-y-4 border-t pt-4">
        <h3 className="text-sm font-medium">{t("sectionInventoryUsage")}</h3>
        {toggle(INVENTORY_TOGGLE)}
        <div className="space-y-4">{USAGE_TOGGLES.map(toggle)}</div>
      </section>
      <PrivacyReportingSection policy={policy} disabled={disabled} t={t} />
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
