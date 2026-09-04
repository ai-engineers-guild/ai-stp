import type { FormEventHandler, ReactNode } from "react";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { MutationReference } from "@/components/molecules/mutation-reference";

import type { ReportTopic } from "./report-form";

export type ReportFormLabels = {
  create: string;
  submitting: string;
  preview: string;
  previewHint: string;
  consent: string;
  diagnostics: string;
  vulnerability: string;
  objectKind: string;
  stableId: string;
  version: string;
  digest: string;
  errorCode: string;
  needPreview: string;
  created: string;
  referenceId: string;
  topic: string;
  subject: string;
  message: string;
  evidence: string;
  author: string;
  recipient: string;
  serviceName: string;
  primaryUrl: string;
  descriptionRu: string;
  descriptionEn: string;
  sourceUrl: string;
  countryCodes: string;
  countryCode: string;
  countryNameRu: string;
  countryNameEn: string;
  topics: Record<ReportTopic, string>;
};

export type ReportFormDefaults = {
  topic: ReportTopic;
  objectKind: "component" | "setup" | "";
  stableId: string;
  version: string;
  contentDigest: string;
  authorAccountId: string;
  recipientAccountId: string;
};

export type ReportFormValues = {
  errorCode: string;
  subject: string;
  message: string;
  evidence: string;
  authorAccountId: string;
  recipientAccountId: string;
  serviceName: string;
  primaryUrl: string;
  descriptionRu: string;
  descriptionEn: string;
  sourceUrl: string;
  countryCodes: string;
  countryCode: string;
  countryNameRu: string;
  countryNameEn: string;
};

export type ReportFormSetters = {
  [Key in keyof ReportFormValues]: (value: string) => void;
};

export function ReportFormLayout({
  onSubmit,
  children,
}: {
  onSubmit: FormEventHandler<HTMLFormElement>;
  children: ReactNode;
}) {
  return (
    <form
      className="border-border mx-auto max-w-lg space-y-4 rounded-lg border p-4"
      onSubmit={onSubmit}
    >
      {children}
    </form>
  );
}

export function ReportTopicSelector({
  topic,
  labels,
  onChange,
  topics,
}: {
  topic: ReportTopic;
  labels: ReportFormLabels;
  onChange: (topic: ReportTopic) => void;
  topics: ReportTopic[];
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor="report-topic">{labels.topic}</Label>
      <select
        id="report-topic"
        className="border-input bg-background w-full rounded-sm border px-2 py-1 text-sm"
        value={topic}
        onChange={(event) => {
          onChange(event.target.value as ReportTopic);
        }}
      >
        {topics.map((value) => (
          <option key={value} value={value}>
            {labels.topics[value]}
          </option>
        ))}
      </select>
    </div>
  );
}

export function ReportObjectSummary({
  defaults,
  labels,
}: {
  defaults: ReportFormDefaults;
  labels: ReportFormLabels;
}) {
  const fields = [
    [labels.objectKind, defaults.objectKind],
    [labels.stableId, defaults.stableId],
    [labels.version, defaults.version],
    [labels.digest, defaults.contentDigest],
  ];
  return (
    <dl className="bg-muted/40 border-border space-y-2 rounded-md border p-3 font-mono text-xs">
      {fields.map(([label, value]) => (
        <div key={label}>
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="break-all">{value || "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ReportTopicFields({
  topic,
  labels,
  values,
  setters,
}: {
  topic: ReportTopic;
  labels: ReportFormLabels;
  values: ReportFormValues;
  setters: ReportFormSetters;
}) {
  return (
    <>
      {topic === "other" ? (
        <div className="space-y-2">
          <Label htmlFor="report-subject">{labels.subject}</Label>
          <Input
            id="report-subject"
            value={values.subject}
            onChange={(event) => {
              setters.subject(event.target.value);
            }}
            maxLength={160}
          />
        </div>
      ) : null}

      {topic === "author_complaint" || topic === "verification_request" ? (
        <div className="space-y-2">
          <Label htmlFor="report-author">{labels.author}</Label>
          <Input
            id="report-author"
            className="font-mono text-xs"
            value={values.authorAccountId}
            onChange={(event) => {
              setters.authorAccountId(event.target.value);
            }}
            maxLength={64}
          />
        </div>
      ) : null}

      {topic === "ownership_transfer" ? (
        <div className="space-y-2">
          <Label htmlFor="report-recipient">{labels.recipient}</Label>
          <Input
            id="report-recipient"
            className="font-mono text-xs"
            value={values.recipientAccountId}
            onChange={(event) => {
              setters.recipientAccountId(event.target.value);
            }}
            maxLength={64}
          />
        </div>
      ) : null}

      {topic === "service_request" ? (
        <div className="space-y-3">
          <Input
            aria-label={labels.serviceName}
            value={values.serviceName}
            onChange={(event) => {
              setters.serviceName(event.target.value);
            }}
            placeholder={labels.serviceName}
          />
          <Input
            aria-label={labels.primaryUrl}
            value={values.primaryUrl}
            onChange={(event) => {
              setters.primaryUrl(event.target.value);
            }}
            placeholder={labels.primaryUrl}
          />
          <Input
            aria-label={labels.sourceUrl}
            value={values.sourceUrl}
            onChange={(event) => {
              setters.sourceUrl(event.target.value);
            }}
            placeholder={labels.sourceUrl}
          />
          <textarea
            aria-label={labels.descriptionRu}
            className="border-input bg-background min-h-16 w-full rounded-sm border px-2 py-1 text-sm"
            value={values.descriptionRu}
            onChange={(event) => {
              setters.descriptionRu(event.target.value);
            }}
            placeholder={labels.descriptionRu}
          />
          <textarea
            aria-label={labels.descriptionEn}
            className="border-input bg-background min-h-16 w-full rounded-sm border px-2 py-1 text-sm"
            value={values.descriptionEn}
            onChange={(event) => {
              setters.descriptionEn(event.target.value);
            }}
            placeholder={labels.descriptionEn}
          />
          <Input
            aria-label={labels.countryCodes}
            value={values.countryCodes}
            onChange={(event) => {
              setters.countryCodes(event.target.value);
            }}
            placeholder={labels.countryCodes}
          />
        </div>
      ) : null}

      {topic === "country_request" ? (
        <div className="space-y-3">
          <Input
            aria-label={labels.countryCode}
            value={values.countryCode}
            onChange={(event) => {
              setters.countryCode(event.target.value);
            }}
            placeholder={labels.countryCode}
            maxLength={2}
          />
          <Input
            aria-label={labels.countryNameRu}
            value={values.countryNameRu}
            onChange={(event) => {
              setters.countryNameRu(event.target.value);
            }}
            placeholder={labels.countryNameRu}
          />
          <Input
            aria-label={labels.countryNameEn}
            value={values.countryNameEn}
            onChange={(event) => {
              setters.countryNameEn(event.target.value);
            }}
            placeholder={labels.countryNameEn}
          />
        </div>
      ) : null}
    </>
  );
}

export function ReportTextFields({
  topic,
  labels,
  values,
  setters,
  diagnostics,
  onDiagnosticsChange,
}: {
  topic: ReportTopic;
  labels: ReportFormLabels;
  values: ReportFormValues;
  setters: ReportFormSetters;
  diagnostics: string;
  onDiagnosticsChange: (value: string) => void;
}) {
  return (
    <>
      {topic !== "object_report" ? (
        <>
          <div className="space-y-2">
            <Label htmlFor="report-message">{labels.message}</Label>
            <textarea
              id="report-message"
              className="border-input bg-background min-h-20 w-full rounded-sm border px-2 py-1 text-sm"
              value={values.message}
              maxLength={2000}
              onChange={(event) => {
                setters.message(event.target.value);
              }}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="report-evidence">{labels.evidence}</Label>
            <textarea
              id="report-evidence"
              className="border-input bg-background min-h-16 w-full rounded-sm border px-2 py-1 text-sm"
              value={values.evidence}
              maxLength={4000}
              onChange={(event) => {
                setters.evidence(event.target.value);
              }}
            />
          </div>
        </>
      ) : null}

      <div className="space-y-2">
        <Label htmlFor="report-error-code">{labels.errorCode}</Label>
        <Input
          id="report-error-code"
          className="font-mono text-xs"
          value={values.errorCode}
          onChange={(event) => {
            setters.errorCode(event.target.value);
          }}
          maxLength={64}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="report-diagnostics">{labels.diagnostics}</Label>
        <textarea
          id="report-diagnostics"
          className="border-input bg-background min-h-28 w-full rounded-sm border px-2 py-1 font-mono text-xs"
          value={diagnostics}
          maxLength={4000}
          onChange={(event) => {
            onDiagnosticsChange(event.target.value);
          }}
        />
        <p className="text-muted-foreground text-xs">{labels.previewHint}</p>
      </div>
    </>
  );
}

export function ReportFormActions({
  labels,
  pending,
  canSubmit,
  previewed,
  consent,
  vulnerability,
  topic,
  diagnostics,
  error,
  done,
  operationId,
  onPreview,
  onConsent,
  onVulnerability,
}: {
  labels: ReportFormLabels;
  pending: boolean;
  canSubmit: boolean;
  previewed: boolean;
  consent: boolean;
  vulnerability: boolean;
  topic: ReportTopic;
  diagnostics: string;
  error: string | null;
  done: boolean;
  operationId: string | null;
  onPreview: () => void;
  onConsent: (value: boolean) => void;
  onVulnerability: (value: boolean) => void;
}) {
  return (
    <>
      <Button type="button" variant="outline" onClick={onPreview}>
        {labels.preview}
      </Button>
      {previewed ? (
        <pre className="overflow-x-auto rounded border p-3 font-mono text-xs">
          {diagnostics || "—"}
        </pre>
      ) : null}
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={consent}
          onChange={(event) => {
            onConsent(event.target.checked);
          }}
        />
        <span>{labels.consent}</span>
      </label>
      {topic === "object_report" ? (
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={vulnerability}
            onChange={(event) => {
              onVulnerability(event.target.checked);
            }}
          />
          <span>{labels.vulnerability}</span>
        </label>
      ) : null}
      <Button type="submit" disabled={pending || !canSubmit}>
        {pending ? labels.submitting : labels.create}
      </Button>
      {done ? <p className="text-sm">{labels.created}</p> : null}
      <MutationReference label={labels.referenceId} operationId={operationId} />
      {error ? (
        <p className="text-destructive text-sm" role="alert">
          {error}
        </p>
      ) : null}
    </>
  );
}
