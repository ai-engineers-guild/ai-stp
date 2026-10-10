"use client";

import { useRef } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import { InfoNote } from "@/components/molecules/info-note";
import { NavigationTabs } from "@/components/molecules/navigation-tabs";
import { SettingsSection } from "@/components/molecules/settings-section";
import { SwitchRow } from "@/components/molecules/switch-row";
import {
  useGovernanceMutation,
  type GovernanceAuthority,
} from "@/components/organisms/corporate-governance-controls";
import {
  AdvancedDisclosure,
  PresetCadenceField,
  TelemetryRetentionTab,
  UnitSecondsField,
  durationLabel,
} from "@/components/organisms/corporate-telemetry-policy-fields";
import type {
  CorporateTelemetryPolicyRequest,
  CorporateTelemetryPolicyView,
} from "@/lib/api/generated/types.gen";

export type TelemetryPolicyTab = "heartbeat" | "usage" | "retention";

type T = ReturnType<typeof useTranslations>;

// Presets are display conveniences; the submitted value stays in seconds.
const HEARTBEAT_INTERVAL_PRESETS = [60, 300, 900, 3600, 21600, 86400] as const;
const HEARTBEAT_STALE_PRESETS = [3600, 21600, 86400, 259200, 604800] as const;

type PolicyEffect = Omit<
  CorporateTelemetryPolicyRequest,
  "schema_version" | "authorization_revision" | "idempotency_key" | "reason"
>;

function retentionDefaults(policy: CorporateTelemetryPolicyView | null) {
  return {
    raw_retention_days: policy?.raw_retention_days ?? 90,
    aggregate_retention_days: policy?.aggregate_retention_days ?? 365,
    legal_basis: policy?.legal_basis ?? "legitimate_interest",
    notice_text: policy?.notice_text ?? null,
    notice_revision: policy?.notice_revision ?? 0,
    report_timezone: policy?.report_timezone ?? "UTC",
  };
}

function heartbeatDefaults(policy: CorporateTelemetryPolicyView | null) {
  return {
    heartbeat_enabled: policy?.heartbeat_enabled ?? true,
    heartbeat_interval_seconds: policy?.heartbeat_interval_seconds ?? 21600,
    heartbeat_retry_base_seconds: policy?.heartbeat_retry_base_seconds ?? 60,
    heartbeat_retry_max_seconds: policy?.heartbeat_retry_max_seconds ?? 3600,
    heartbeat_stale_after_seconds: policy?.heartbeat_stale_after_seconds ?? 86400,
  };
}

function usageDefaults(policy: CorporateTelemetryPolicyView | null) {
  return {
    inventory_scan_enabled: policy?.inventory_scan_enabled ?? false,
    usage_collection_enabled: policy?.usage_collection_enabled ?? false,
    usage_registration_required: policy?.usage_registration_required ?? false,
  };
}

function policyDefaults(policy: CorporateTelemetryPolicyView | null): PolicyEffect {
  return {
    ...retentionDefaults(policy),
    ...heartbeatDefaults(policy),
    ...usageDefaults(policy),
    expected_policy_revision: policy?.policy_version ?? 0,
  };
}

function parseBool(data: FormData, name: string): boolean | null {
  const value = data.get(name);
  return value === "true" ? true : value === "false" ? false : null;
}

function parseInt(data: FormData, name: string): number | null {
  const value = data.get(name);
  if (typeof value !== "string") return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

/** Each tab edits only its own fields; the PUT body merges over the known policy. */
function parseTabForm(tab: TelemetryPolicyTab, data: FormData): Partial<PolicyEffect> | null {
  if (tab === "heartbeat") {
    const values = {
      heartbeat_enabled: parseBool(data, "heartbeat_enabled"),
      heartbeat_interval_seconds: parseInt(data, "heartbeat_interval_seconds"),
      heartbeat_retry_base_seconds: parseInt(data, "heartbeat_retry_base_seconds"),
      heartbeat_retry_max_seconds: parseInt(data, "heartbeat_retry_max_seconds"),
      heartbeat_stale_after_seconds: parseInt(data, "heartbeat_stale_after_seconds"),
    };
    return Object.values(values).includes(null) ? null : values;
  }
  if (tab === "usage") {
    const usageCollection = parseBool(data, "usage_collection_enabled");
    const usageRegistration = parseBool(data, "usage_registration_required");
    const inventoryScan = parseBool(data, "inventory_scan_enabled");
    if (usageCollection === null || usageRegistration === null || inventoryScan === null)
      return null;
    if (usageRegistration && !usageCollection) return null;
    return {
      inventory_scan_enabled: inventoryScan,
      usage_collection_enabled: usageCollection,
      usage_registration_required: usageRegistration,
    };
  }
  const legalBasis = data.get("legal_basis");
  const rawNotice = data.get("notice_text");
  const reportTimezone = data.get("report_timezone");
  const values = {
    raw_retention_days: parseInt(data, "raw_retention_days"),
    aggregate_retention_days: parseInt(data, "aggregate_retention_days"),
  };
  if (
    typeof legalBasis !== "string" ||
    (legalBasis !== "consent" &&
      legalBasis !== "contract" &&
      legalBasis !== "legitimate_interest") ||
    typeof rawNotice !== "string" ||
    typeof reportTimezone !== "string" ||
    !reportTimezone ||
    Object.values(values).includes(null)
  )
    return null;
  return {
    ...values,
    legal_basis: legalBasis,
    notice_text: rawNotice || null,
    report_timezone: reportTimezone,
  } as Partial<PolicyEffect>;
}

function switchStatus(t: T, onHint: string, offHint: string) {
  return {
    on: t("policyEnabled"),
    off: t("policyDisabled"),
    onHint,
    offHint,
  };
}

function HeartbeatTab({
  policy,
  disabled,
  t,
}: {
  policy: CorporateTelemetryPolicyView | null;
  disabled: boolean;
  t: T;
}) {
  const heartbeatOn = policy?.heartbeat_enabled ?? true;
  const interval = policy?.heartbeat_interval_seconds ?? 21600;
  const stale = policy?.heartbeat_stale_after_seconds ?? 86400;
  const retryBase = policy?.heartbeat_retry_base_seconds ?? 60;
  const retryMax = policy?.heartbeat_retry_max_seconds ?? 3600;
  return (
    <>
      <SettingsSection
        header={
          <SwitchRow
            id="heartbeat-enabled"
            name="heartbeat_enabled"
            icon="activity"
            label={t("heartbeatCardTitle")}
            description={t("heartbeatCardDescription")}
            value={heartbeatOn}
            disabled={disabled}
            status={switchStatus(t, t("heartbeatEnabledState"), t("heartbeatDisabledState"))}
          />
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <PresetCadenceField
            id="heartbeat-interval"
            name="heartbeat_interval_seconds"
            label={t("heartbeatInterval")}
            hint={t("heartbeatIntervalHint")}
            presets={HEARTBEAT_INTERVAL_PRESETS}
            seconds={interval}
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
            seconds={stale}
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
              seconds={retryBase}
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
              seconds={retryMax}
              unit={60}
              min={1}
              max={10080}
              disabled={disabled}
            />
          </div>
        </AdvancedDisclosure>
      </SettingsSection>
      <SettingsSection
        icon="clock"
        title={t("schedulerTitle")}
        description={t("schedulerDescription")}
      >
        <dl className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-[minmax(10rem,auto)_1fr]">
          <dt className="text-muted-foreground">{t("schedulerTickCadence")}</dt>
          <dd>
            {t("schedulerFollowsInterval")} · {durationLabel(interval, t)}
          </dd>
          <dt className="text-muted-foreground">{t("schedulerRetrySchedule")}</dt>
          <dd>
            {durationLabel(retryBase, t)} →{" "}
            {t("schedulerRetryMax", { value: durationLabel(retryMax, t) })}
          </dd>
          <dt className="text-muted-foreground">{t("schedulerStaleAfter")}</dt>
          <dd>{durationLabel(stale, t)}</dd>
          <dt className="text-muted-foreground">{t("schedulerKind")}</dt>
          <dd>{t("schedulerOsManaged")}</dd>
        </dl>
        <InfoNote className="mt-4">{t("schedulerNote")}</InfoNote>
      </SettingsSection>
    </>
  );
}

function UsageTab({
  policy,
  disabled,
  t,
}: {
  policy: CorporateTelemetryPolicyView | null;
  disabled: boolean;
  t: T;
}) {
  const inventoryOn = policy?.inventory_scan_enabled ?? false;
  const usageOn = policy?.usage_collection_enabled ?? false;
  const registrationOn = policy?.usage_registration_required ?? false;
  return (
    <>
      <SettingsSection
        icon="technology"
        title={t("usageCardTitle")}
        description={t("usageCardDescription")}
      >
        <div className="space-y-4">
          <SwitchRow
            id="inventory-scan-enabled"
            name="inventory_scan_enabled"
            label={t("inventoryScanReporting")}
            description={t("inventoryScanDescription")}
            value={inventoryOn}
            disabled={disabled}
            status={switchStatus(
              t,
              t("inventoryScanEnabledState"),
              t("inventoryScanDisabledState"),
            )}
          />
          <SwitchRow
            id="usage-collection-enabled"
            name="usage_collection_enabled"
            label={t("usageCollectionReporting")}
            description={t("usageCollectionDescription")}
            value={usageOn}
            disabled={disabled}
            status={switchStatus(
              t,
              t("usageCollectionEnabledState"),
              t("usageCollectionDisabledState"),
            )}
          />
          <SwitchRow
            id="usage-registration-required"
            name="usage_registration_required"
            label={t("usageRegistrationRequired")}
            description={t("usageRegistrationDescription")}
            value={registrationOn}
            disabled={disabled}
            status={switchStatus(
              t,
              t("usageRegistrationEnabledState"),
              t("usageRegistrationDisabledState"),
            )}
          />
        </div>
        <InfoNote className="mt-4">{t("usageRegistrationNote")}</InfoNote>
      </SettingsSection>
      <SettingsSection icon="info" title={t("usageAboutTitle")} description={t("usageAboutBody")}>
        <InfoNote>{t("usageAboutNote")}</InfoNote>
      </SettingsSection>
    </>
  );
}

export function CorporateTelemetryPolicyControls({
  policy,
  tab = "heartbeat",
  canManage = true,
  ...authority
}: GovernanceAuthority & {
  policy: CorporateTelemetryPolicyView | null;
  tab?: TelemetryPolicyTab;
  canManage?: boolean;
}) {
  const t = useTranslations("technology");
  const revision = useRef(policy?.policy_version ?? 0);
  const mutation = useGovernanceMutation(authority);
  const disabled = mutation.busy || !canManage;
  const tabs: TelemetryPolicyTab[] = ["heartbeat", "usage", "retention"];
  return (
    <div className="space-y-6">
      <NavigationTabs
        variant="underline"
        ariaLabel={t("telemetryPolicy")}
        items={tabs.map((key) => ({
          key,
          href: `/corporate/admin/telemetry?tab=${key}`,
          label: t(`telemetryTab.${key}`),
          active: key === tab,
        }))}
      />
      <form
        className="space-y-6"
        aria-busy={mutation.busy}
        onSubmit={(event) => {
          event.preventDefault();
          const parsed = parseTabForm(tab, new FormData(event.currentTarget));
          if (!parsed) return;
          const base = policyDefaults(policy);
          const effect = {
            ...base,
            ...parsed,
            expected_policy_revision: revision.current,
          } satisfies PolicyEffect;
          effect.notice_revision =
            base.notice_revision + (effect.notice_text !== (policy?.notice_text ?? null) ? 1 : 0);
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
        <fieldset disabled={disabled} className="space-y-6 border-0 p-0">
          {tab === "heartbeat" ? (
            <HeartbeatTab policy={policy} disabled={disabled} t={t} />
          ) : tab === "usage" ? (
            <UsageTab policy={policy} disabled={disabled} t={t} />
          ) : (
            <TelemetryRetentionTab policy={policy} disabled={disabled} t={t} />
          )}
        </fieldset>
        {canManage ? (
          <div className="flex items-center justify-end gap-4">
            {mutation.message && (
              <p className="text-muted-foreground text-sm" role="status">
                {mutation.message}
              </p>
            )}
            <Button type="submit" size="lg" disabled={mutation.busy}>
              {t(mutation.busy ? "saving" : "saveChanges")}
            </Button>
          </div>
        ) : null}
      </form>
    </div>
  );
}
