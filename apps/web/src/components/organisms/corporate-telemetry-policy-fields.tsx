"use client";

import { useState } from "react";
import type { useTranslations } from "next-intl";

import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Switch } from "@/components/atoms/switch";
import { Textarea } from "@/components/atoms/textarea";
import type { CorporateTelemetryPolicyView } from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";

type T = ReturnType<typeof useTranslations>;

export const selectClass =
  "border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2";

/** "?" glyph next to a label; the explanation rides the title for pointer
 * users and an sr-only span for assistive tech. */
export function FieldHint({ text }: { text: string }) {
  return (
    <span className="text-muted-foreground inline-flex align-middle" title={text}>
      <Icon name="help" size="sm" />
      <span className="sr-only">{text}</span>
    </span>
  );
}

export function SwitchRow({
  id,
  name,
  label,
  hint,
  value,
  disabled,
}: {
  id: string;
  name: string;
  label: string;
  hint: string | undefined;
  value: boolean;
  disabled: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="flex items-center gap-1">
        <Label htmlFor={id} className="font-normal">
          {label}
        </Label>
        {hint ? <FieldHint text={hint} /> : null}
      </span>
      <Switch id={id} name={name} defaultChecked={value} disabled={disabled} aria-label={label} />
    </div>
  );
}

function durationLabel(seconds: number, t: T): string {
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
      <span className="flex items-center gap-1">
        <Label htmlFor={id}>{label}</Label>
        {hint ? <FieldHint text={hint} /> : null}
      </span>
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
      <span className="flex items-center gap-1">
        <Label htmlFor={id}>{label}</Label>
        {hint ? <FieldHint text={hint} /> : null}
      </span>
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

export function PrivacyReportingSection({
  policy,
  disabled,
  t,
}: {
  policy: CorporateTelemetryPolicyView | null;
  disabled: boolean;
  t: T;
}) {
  return (
    <section className="border-border space-y-4 border-t pt-4">
      <h3 className="text-sm font-medium">{t("sectionPrivacyReporting")}</h3>
      <div className="space-y-2">
        <span className="flex items-center gap-1">
          <Label htmlFor="telemetry-legal-basis">{t("telemetryLegalBasis")}</Label>
          <FieldHint text={t("telemetryLegalBasisHint")} />
        </span>
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
        <span className="flex items-center gap-1">
          <Label htmlFor="telemetry-raw-retention">{t("telemetryRawRetention")}</Label>
          <FieldHint text={t("telemetryRawRetentionHint")} />
        </span>
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
      <AdvancedDisclosure title={t("advanced")}>
        <div className="space-y-2">
          <span className="flex items-center gap-1">
            <Label htmlFor="telemetry-aggregate-retention">
              {t("telemetryAggregateRetention")}
            </Label>
            <FieldHint text={t("telemetryAggregateRetentionHint")} />
          </span>
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
        <div className="space-y-2">
          <span className="flex items-center gap-1">
            <Label htmlFor="report-timezone">{t("reportTimezone")}</Label>
            <FieldHint text={t("reportTimezoneHint")} />
          </span>
          <Input
            id="report-timezone"
            name="report_timezone"
            required
            maxLength={64}
            defaultValue={policy?.report_timezone ?? "UTC"}
            disabled={disabled}
          />
        </div>
      </AdvancedDisclosure>
    </section>
  );
}
