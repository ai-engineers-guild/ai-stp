"use client";

import { useState, useSyncExternalStore } from "react";
import type { useTranslations } from "next-intl";

import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import { FieldHint } from "@/components/molecules/field-hint";
import { InfoNote } from "@/components/molecules/info-note";
import { SettingsSection } from "@/components/molecules/settings-section";

import type { CorporateTelemetryPolicyView } from "@/lib/api/generated/types.gen";

type T = ReturnType<typeof useTranslations>;

export const selectClass =
  "border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2";

export { FieldHint };

const RETENTION_PRESETS = [30, 90, 180, 365, 730, 1095] as const;

// Memoized snapshots for useSyncExternalStore: the hook polls its snapshot, so
// each call must return a stable reference for the same input.
const NO_SUBSCRIBE = () => () => {};
const zoneCache = new Map<string, readonly string[]>();
const singleZoneCache = new Map<string, readonly string[]>();

function browserZones(current: string): readonly string[] {
  let zones = zoneCache.get(current);
  if (!zones) {
    let all: readonly string[] = [];
    try {
      all = Intl.supportedValuesOf("timeZone");
    } catch {
      // Older runtimes lack supportedValuesOf; the current zone alone is enough.
    }
    // Some ICU builds omit "UTC"; the select must always contain its own value,
    // otherwise an untouched field silently submits the first listed zone.
    zones = all.includes(current) ? all : [current, ...all];
    zoneCache.set(current, zones);
  }
  return zones;
}

function initialZones(current: string): readonly string[] {
  let zones = singleZoneCache.get(current);
  if (!zones) {
    zones = [current];
    singleZoneCache.set(current, zones);
  }
  return zones;
}

export function durationLabel(seconds: number, t: T): string {
  if (seconds % 86400 === 0) return t("daysLabel", { count: seconds / 86400 });
  if (seconds % 3600 === 0) return t("hoursLabel", { count: seconds / 3600 });
  return t("minutesLabel", { count: Math.max(1, Math.round(seconds / 60)) });
}

/** Preset picker for a *_seconds field: common durations as friendly units,
 * "custom" falls back to a numeric input in the field's own unit. The
 * submitted hidden value is always seconds. */
export function PresetCadenceField({
  id,
  name,
  label,
  hint,
  presets,
  seconds,
  customUnit,
  customLabelKey,
  customMin,
  customMax,
  disabled,
  t,
}: {
  id: string;
  name: string;
  label: string;
  hint: string | undefined;
  presets: readonly number[];
  seconds: number;
  customUnit: number;
  customLabelKey: string;
  customMin: number;
  customMax: number;
  disabled: boolean;
  t: T;
}) {
  const matched = presets.includes(seconds);
  const [choice, setChoice] = useState(matched ? String(seconds) : "custom");
  const [custom, setCustom] = useState(
    Math.min(customMax, Math.max(customMin, Math.round(seconds / customUnit))),
  );
  const effective = choice === "custom" ? custom * customUnit : Number(choice);
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <input type="hidden" name={name} value={effective} />
      <select
        id={id}
        value={choice}
        disabled={disabled}
        className={selectClass}
        onChange={(event) => {
          setChoice(event.target.value);
        }}
      >
        {presets.map((preset) => (
          <option key={preset} value={preset}>
            {durationLabel(preset, t)}
          </option>
        ))}
        <option value="custom">{t("custom")}</option>
      </select>
      {choice === "custom" && (
        <Input
          type="number"
          min={customMin}
          max={customMax}
          required
          value={custom}
          disabled={disabled}
          aria-label={t(customLabelKey)}
          onChange={(event) => {
            setCustom(Number(event.target.value));
          }}
        />
      )}
      {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
    </div>
  );
}

/** Preset picker for a *_days field: the submitted hidden value is days. */
export function PresetDaysField({
  id,
  name,
  label,
  hint,
  presets,
  days,
  customMin = 1,
  customMax = 3650,
  disabled,
  t,
}: {
  id: string;
  name: string;
  label: string;
  hint: string | undefined;
  presets: readonly number[];
  days: number;
  customMin?: number;
  customMax?: number;
  disabled: boolean;
  t: T;
}) {
  const matched = presets.includes(days);
  const [choice, setChoice] = useState(matched ? String(days) : "custom");
  const [custom, setCustom] = useState(Math.min(customMax, Math.max(customMin, days)));
  const effective = choice === "custom" ? custom : Number(choice);
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <input type="hidden" name={name} value={effective} />
      <select
        id={id}
        value={choice}
        disabled={disabled}
        className={selectClass}
        onChange={(event) => {
          setChoice(event.target.value);
        }}
      >
        {presets.map((preset) => (
          <option key={preset} value={preset}>
            {t("daysLabel", { count: preset })}
          </option>
        ))}
        <option value="custom">{t("custom")}</option>
      </select>
      {choice === "custom" && (
        <Input
          type="number"
          min={customMin}
          max={customMax}
          required
          value={custom}
          disabled={disabled}
          aria-label={t("customRetentionDays")}
          onChange={(event) => {
            setCustom(Number(event.target.value));
          }}
        />
      )}
      {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
    </div>
  );
}

/** Plain numeric field for a *_seconds value displayed in another unit;
 * the hidden input keeps the contract in seconds. */
export function UnitSecondsField({
  id,
  name,
  label,
  hint,
  seconds,
  unit,
  min,
  max,
  disabled,
}: {
  id: string;
  name: string;
  label: string;
  hint: string | undefined;
  seconds: number;
  unit: number;
  min: number;
  max: number;
  disabled: boolean;
}) {
  const [value, setValue] = useState(Math.round(seconds / unit));
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <input type="hidden" name={name} value={value * unit} />
      <Input
        id={id}
        type="number"
        min={min}
        max={max}
        required
        value={value}
        disabled={disabled}
        onChange={(event) => {
          setValue(Number(event.target.value));
        }}
      />
      {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
    </div>
  );
}

export function AdvancedDisclosure({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <details className="border-border rounded-md border px-4 py-3">
      <summary className="text-muted-foreground cursor-pointer text-sm font-medium">
        {title}
      </summary>
      <div className="mt-4 space-y-4">{children}</div>
    </details>
  );
}

/** Data-retention tab: legal basis, retention windows, timezone, and notice. */
export function TelemetryRetentionTab({
  policy,
  disabled,
  t,
}: {
  policy: CorporateTelemetryPolicyView | null;
  disabled: boolean;
  t: T;
}) {
  const current = policy?.report_timezone ?? "UTC";
  // ICU lists differ between the server runtime and each browser, so the full
  // option set mounts client-side only; SSR and first render show the current
  // value alone — identical markup, no hydration mismatch.
  const timezones = useSyncExternalStore(
    NO_SUBSCRIBE,
    () => browserZones(current),
    () => initialZones(current),
  );
  return (
    <>
      <SettingsSection
        icon="technology"
        title={t("retentionCardTitle")}
        description={t("retentionCardDescription")}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="telemetry-legal-basis">{t("telemetryLegalBasis")}</Label>
            <select
              id="telemetry-legal-basis"
              name="legal_basis"
              required
              defaultValue={policy?.legal_basis ?? ""}
              disabled={disabled}
              className={selectClass}
            >
              <option value="" disabled>
                {t("chooseTelemetryLegalBasis")}
              </option>
              <option value="consent">{t("telemetryBasisConsent")}</option>
              <option value="contract">{t("telemetryBasisContract")}</option>
              <option value="legitimate_interest">{t("telemetryBasisLegitimateInterest")}</option>
            </select>
            <p className="text-muted-foreground text-xs">{t("telemetryLegalBasisCaption")}</p>
          </div>
          <PresetDaysField
            id="telemetry-raw-retention"
            name="raw_retention_days"
            label={t("telemetryRawRetention")}
            hint={t("telemetryRawRetentionCaption")}
            presets={RETENTION_PRESETS}
            days={policy?.raw_retention_days ?? 90}
            disabled={disabled}
            t={t}
          />
        </div>
      </SettingsSection>
      <SettingsSection
        icon="setup"
        title={t("advancedSettingsTitle")}
        description={t("advancedSettingsDescription")}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-4">
            <PresetDaysField
              id="telemetry-aggregate-retention"
              name="aggregate_retention_days"
              label={t("telemetryAggregateRetention")}
              hint={t("telemetryAggregateRetentionCaption")}
              presets={RETENTION_PRESETS}
              days={policy?.aggregate_retention_days ?? 365}
              disabled={disabled}
              t={t}
            />
            <div className="space-y-2">
              <Label htmlFor="report-timezone">{t("reportTimezone")}</Label>
              <select
                id="report-timezone"
                name="report_timezone"
                required
                defaultValue={current}
                disabled={disabled}
                className={selectClass}
              >
                {timezones.map((zone) => (
                  <option key={zone} value={zone}>
                    {zone}
                  </option>
                ))}
              </select>
              <p className="text-muted-foreground text-xs">{t("reportTimezoneCaption")}</p>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="telemetry-notice">{t("telemetryNotice")}</Label>
            <Textarea
              id="telemetry-notice"
              name="notice_text"
              maxLength={4000}
              defaultValue={policy?.notice_text ?? ""}
              disabled={disabled}
              className="min-h-24"
            />
            <p className="text-muted-foreground text-xs">{t("telemetryNoticeCaption")}</p>
          </div>
        </div>
        <InfoNote className="mt-4">{t("telemetryScopeNote")}</InfoNote>
      </SettingsSection>
    </>
  );
}
