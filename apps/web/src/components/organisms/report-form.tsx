"use client";

import { useState, useTransition, type FormEvent } from "react";
import { useRouter } from "@/lib/i18n/navigation";

import { createReportAction } from "@/actions/reports";
import {
  ReportFormActions,
  ReportFormLayout,
  ReportObjectSummary,
  ReportTextFields,
  ReportTopicFields,
  ReportTopicSelector,
  type ReportFormDefaults,
  type ReportFormLabels,
  type ReportFormSetters,
  type ReportFormValues,
} from "./report-form-sections";

export type ReportTopic =
  | "object_report"
  | "service_request"
  | "country_request"
  | "component_complaint"
  | "author_complaint"
  | "ownership_transfer"
  | "verification_request"
  | "other";

type ReportFormProps = {
  csrfToken: string;
  locale: "ru" | "en";
  defaults: ReportFormDefaults;
  labels: ReportFormLabels;
};

const MAX_DIAGNOSTICS = 4000;
const TOPICS: ReportTopic[] = [
  "object_report",
  "component_complaint",
  "author_complaint",
  "ownership_transfer",
  "verification_request",
  "other",
  "service_request",
  "country_request",
];

type ReportActionInput = Parameters<typeof createReportAction>[0];

function canSubmitReport(
  topic: ReportTopic,
  defaults: ReportFormDefaults,
  values: ReportFormValues,
  previewed: boolean,
  consent: boolean,
): boolean {
  const objectReady = [
    defaults.objectKind === "component" || defaults.objectKind === "setup",
    defaults.stableId,
    defaults.version,
    defaults.contentDigest,
  ].every(Boolean);
  const serviceReady = [
    values.serviceName.trim(),
    values.primaryUrl.trim(),
    values.descriptionRu.trim(),
    values.descriptionEn.trim(),
    values.sourceUrl.trim(),
  ].every(Boolean);
  const countryReady = [
    values.countryCode.trim(),
    values.countryNameRu.trim(),
    values.countryNameEn.trim(),
  ].every(Boolean);
  const requirements: Record<ReportTopic, boolean> = {
    object_report: objectReady,
    component_complaint: Boolean(defaults.stableId),
    ownership_transfer: [defaults.stableId, values.recipientAccountId, values.message.trim()].every(
      Boolean,
    ),
    author_complaint: Boolean(values.authorAccountId),
    verification_request: Boolean(values.authorAccountId),
    service_request: serviceReady,
    country_request: countryReady,
    other: Boolean(values.subject.trim()),
  };
  return [previewed, consent, requirements[topic]].every(Boolean);
}

function buildReportActionInput({
  csrfToken,
  locale,
  topic,
  defaults,
  diagnostics,
  previewed,
  vulnerability,
  values,
}: {
  csrfToken: string;
  locale: "ru" | "en";
  topic: ReportTopic;
  defaults: ReportFormDefaults;
  diagnostics: string;
  previewed: boolean;
  vulnerability: boolean;
  values: ReportFormValues;
}): ReportActionInput {
  return {
    csrfToken,
    topic,
    locale,
    objectKind: defaults.objectKind || "component",
    stableId: defaults.stableId,
    version: defaults.version,
    contentDigest: defaults.contentDigest,
    diagnostics,
    diagnosticsPreviewed: previewed,
    vulnerability: topic === "object_report" && vulnerability,
    ...(values.errorCode ? { errorCode: values.errorCode } : {}),
    subject: values.subject,
    message: values.message,
    evidence: values.evidence,
    authorAccountId: values.authorAccountId,
    recipientAccountId: values.recipientAccountId,
    ...(topic === "service_request"
      ? {
          service: {
            name: values.serviceName,
            primary_url: values.primaryUrl,
            description_ru: values.descriptionRu,
            description_en: values.descriptionEn,
            source_url: values.sourceUrl,
            country_codes: values.countryCodes
              .split(",")
              .map((code) => code.trim().toUpperCase())
              .filter(Boolean),
          },
        }
      : {}),
    ...(topic === "country_request"
      ? {
          country: {
            code: values.countryCode.trim().toUpperCase(),
            name_ru: values.countryNameRu,
            name_en: values.countryNameEn,
          },
        }
      : {}),
  };
}

export function ReportForm({ csrfToken, locale, defaults, labels }: ReportFormProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [topic, setTopic] = useState<ReportTopic>(defaults.topic);
  const [diagnostics, setDiagnostics] = useState("");
  const [previewed, setPreviewed] = useState(false);
  const [consent, setConsent] = useState(false);
  const [vulnerability, setVulnerability] = useState(false);
  const [errorCode, setErrorCode] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [evidence, setEvidence] = useState("");
  const [authorAccountId, setAuthorAccountId] = useState(defaults.authorAccountId);
  const [recipientAccountId, setRecipientAccountId] = useState(defaults.recipientAccountId);
  const [serviceName, setServiceName] = useState("");
  const [primaryUrl, setPrimaryUrl] = useState("");
  const [descriptionRu, setDescriptionRu] = useState("");
  const [descriptionEn, setDescriptionEn] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [countryCodes, setCountryCodes] = useState("");
  const [countryCode, setCountryCode] = useState("");
  const [countryNameRu, setCountryNameRu] = useState("");
  const [countryNameEn, setCountryNameEn] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [operationId, setOperationId] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const values: ReportFormValues = {
    errorCode,
    subject,
    message,
    evidence,
    authorAccountId,
    recipientAccountId,
    serviceName,
    primaryUrl,
    descriptionRu,
    descriptionEn,
    sourceUrl,
    countryCodes,
    countryCode,
    countryNameRu,
    countryNameEn,
  };
  const canSubmit = canSubmitReport(topic, defaults, values, previewed, consent);
  const setters: ReportFormSetters = {
    errorCode: setErrorCode,
    subject: setSubject,
    message: setMessage,
    evidence: setEvidence,
    authorAccountId: setAuthorAccountId,
    recipientAccountId: setRecipientAccountId,
    serviceName: setServiceName,
    primaryUrl: setPrimaryUrl,
    descriptionRu: setDescriptionRu,
    descriptionEn: setDescriptionEn,
    sourceUrl: setSourceUrl,
    countryCodes: setCountryCodes,
    countryCode: setCountryCode,
    countryNameRu: setCountryNameRu,
    countryNameEn: setCountryNameEn,
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!previewed || !consent) {
      setError(labels.needPreview);
      return;
    }
    if (!canSubmit) {
      setError("complete the fields for the selected topic");
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        const result = await createReportAction(
          buildReportActionInput({
            csrfToken,
            topic,
            locale,
            defaults,
            diagnostics,
            previewed,
            vulnerability,
            values,
          }),
        );
        setOperationId(result.operationId);
        setDone(true);
        setDiagnostics("");
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "error");
      }
    });
  };

  const handleTopicChange = (value: ReportTopic) => {
    setTopic(value);
    setPreviewed(false);
    setConsent(false);
  };
  const handleDiagnosticsChange = (value: string) => {
    setDiagnostics(value.slice(0, MAX_DIAGNOSTICS));
    setPreviewed(false);
    setConsent(false);
  };

  return (
    <ReportFormLayout onSubmit={handleSubmit}>
      <ReportTopicSelector
        topic={topic}
        labels={labels}
        topics={TOPICS}
        onChange={handleTopicChange}
      />
      <ReportObjectSummary defaults={defaults} labels={labels} />
      <ReportTopicFields topic={topic} labels={labels} values={values} setters={setters} />
      <ReportTextFields
        topic={topic}
        labels={labels}
        values={values}
        setters={setters}
        diagnostics={diagnostics}
        onDiagnosticsChange={handleDiagnosticsChange}
      />
      <ReportFormActions
        labels={labels}
        pending={pending}
        canSubmit={canSubmit}
        previewed={previewed}
        consent={consent}
        vulnerability={vulnerability}
        topic={topic}
        diagnostics={diagnostics}
        error={error}
        done={done}
        operationId={operationId}
        onPreview={() => {
          setPreviewed(true);
        }}
        onConsent={setConsent}
        onVulnerability={setVulnerability}
      />
    </ReportFormLayout>
  );
}
