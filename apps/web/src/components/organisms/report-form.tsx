"use client";

import { useState, useTransition } from "react";
import { useRouter } from "@/lib/i18n/navigation";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { MutationReference } from "@/components/molecules/mutation-reference";
import { createReportAction } from "@/actions/reports";

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
  defaults: {
    topic: ReportTopic;
    objectKind: "component" | "setup" | "";
    stableId: string;
    version: string;
    contentDigest: string;
    authorAccountId: string;
    recipientAccountId: string;
  };
  labels: {
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

  const objectKind = defaults.objectKind;
  const objectReady =
    (objectKind === "component" || objectKind === "setup") &&
    Boolean(defaults.stableId) &&
    Boolean(defaults.version) &&
    Boolean(defaults.contentDigest);
  const serviceReady =
    Boolean(serviceName.trim()) &&
    Boolean(primaryUrl.trim()) &&
    Boolean(descriptionRu.trim()) &&
    Boolean(descriptionEn.trim()) &&
    Boolean(sourceUrl.trim());
  const countryReady =
    Boolean(countryCode.trim()) && Boolean(countryNameRu.trim()) && Boolean(countryNameEn.trim());
  const canSubmit =
    previewed &&
    consent &&
    (topic !== "object_report" || objectReady) &&
    (topic !== "component_complaint" || Boolean(defaults.stableId)) &&
    (topic !== "ownership_transfer" ||
      Boolean(defaults.stableId && recipientAccountId && message.trim())) &&
    (topic !== "author_complaint" || Boolean(authorAccountId)) &&
    (topic !== "verification_request" || Boolean(authorAccountId)) &&
    (topic !== "service_request" || serviceReady) &&
    (topic !== "country_request" || countryReady) &&
    (topic !== "other" || Boolean(subject.trim()));

  return (
    <form
      className="border-border mx-auto max-w-lg space-y-4 rounded-lg border p-4"
      onSubmit={(event) => {
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
            const result = await createReportAction({
              csrfToken,
              topic,
              locale,
              objectKind: objectKind || "component",
              stableId: defaults.stableId,
              version: defaults.version,
              contentDigest: defaults.contentDigest,
              diagnostics,
              diagnosticsPreviewed: previewed,
              vulnerability: topic === "object_report" && vulnerability,
              ...(errorCode ? { errorCode } : {}),
              subject,
              message,
              evidence,
              authorAccountId,
              recipientAccountId,
              ...(topic === "service_request"
                ? {
                    service: {
                      name: serviceName,
                      primary_url: primaryUrl,
                      description_ru: descriptionRu,
                      description_en: descriptionEn,
                      source_url: sourceUrl,
                      country_codes: countryCodes
                        .split(",")
                        .map((code) => code.trim().toUpperCase())
                        .filter(Boolean),
                    },
                  }
                : {}),
              ...(topic === "country_request"
                ? {
                    country: {
                      code: countryCode.trim().toUpperCase(),
                      name_ru: countryNameRu,
                      name_en: countryNameEn,
                    },
                  }
                : {}),
            });
            setOperationId(result.operationId);
            setDone(true);
            setDiagnostics("");
            router.refresh();
          } catch (err) {
            setError(err instanceof Error ? err.message : "error");
          }
        });
      }}
    >
      <div className="space-y-2">
        <Label htmlFor="report-topic">{labels.topic}</Label>
        <select
          id="report-topic"
          className="border-input bg-background w-full rounded-sm border px-2 py-1 text-sm"
          value={topic}
          onChange={(event) => {
            setTopic(event.target.value as ReportTopic);
            setPreviewed(false);
            setConsent(false);
          }}
        >
          {TOPICS.map((value) => (
            <option key={value} value={value}>
              {labels.topics[value]}
            </option>
          ))}
        </select>
      </div>

      <dl className="bg-muted/40 border-border space-y-2 rounded-md border p-3 font-mono text-xs">
        <div>
          <dt className="text-muted-foreground">{labels.objectKind}</dt>
          <dd>{defaults.objectKind || "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{labels.stableId}</dt>
          <dd className="break-all">{defaults.stableId || "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{labels.version}</dt>
          <dd>{defaults.version || "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{labels.digest}</dt>
          <dd className="break-all">{defaults.contentDigest || "—"}</dd>
        </div>
      </dl>

      {topic === "other" ? (
        <div className="space-y-2">
          <Label htmlFor="report-subject">{labels.subject}</Label>
          <Input
            id="report-subject"
            value={subject}
            onChange={(event) => {
              setSubject(event.target.value);
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
            value={authorAccountId}
            onChange={(event) => {
              setAuthorAccountId(event.target.value);
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
            value={recipientAccountId}
            onChange={(event) => {
              setRecipientAccountId(event.target.value);
            }}
            maxLength={64}
          />
        </div>
      ) : null}

      {topic === "service_request" ? (
        <div className="space-y-3">
          <Input
            aria-label={labels.serviceName}
            value={serviceName}
            onChange={(event) => setServiceName(event.target.value)}
            placeholder={labels.serviceName}
          />
          <Input
            aria-label={labels.primaryUrl}
            value={primaryUrl}
            onChange={(event) => setPrimaryUrl(event.target.value)}
            placeholder={labels.primaryUrl}
          />
          <Input
            aria-label={labels.sourceUrl}
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder={labels.sourceUrl}
          />
          <textarea
            aria-label={labels.descriptionRu}
            className="border-input bg-background min-h-16 w-full rounded-sm border px-2 py-1 text-sm"
            value={descriptionRu}
            onChange={(event) => setDescriptionRu(event.target.value)}
            placeholder={labels.descriptionRu}
          />
          <textarea
            aria-label={labels.descriptionEn}
            className="border-input bg-background min-h-16 w-full rounded-sm border px-2 py-1 text-sm"
            value={descriptionEn}
            onChange={(event) => setDescriptionEn(event.target.value)}
            placeholder={labels.descriptionEn}
          />
          <Input
            aria-label={labels.countryCodes}
            value={countryCodes}
            onChange={(event) => setCountryCodes(event.target.value)}
            placeholder={labels.countryCodes}
          />
        </div>
      ) : null}

      {topic === "country_request" ? (
        <div className="space-y-3">
          <Input
            aria-label={labels.countryCode}
            value={countryCode}
            onChange={(event) => setCountryCode(event.target.value)}
            placeholder={labels.countryCode}
            maxLength={2}
          />
          <Input
            aria-label={labels.countryNameRu}
            value={countryNameRu}
            onChange={(event) => setCountryNameRu(event.target.value)}
            placeholder={labels.countryNameRu}
          />
          <Input
            aria-label={labels.countryNameEn}
            value={countryNameEn}
            onChange={(event) => setCountryNameEn(event.target.value)}
            placeholder={labels.countryNameEn}
          />
        </div>
      ) : null}

      {topic !== "object_report" ? (
        <>
          <div className="space-y-2">
            <Label htmlFor="report-message">{labels.message}</Label>
            <textarea
              id="report-message"
              className="border-input bg-background min-h-20 w-full rounded-sm border px-2 py-1 text-sm"
              value={message}
              maxLength={2000}
              onChange={(event) => {
                setMessage(event.target.value);
              }}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="report-evidence">{labels.evidence}</Label>
            <textarea
              id="report-evidence"
              className="border-input bg-background min-h-16 w-full rounded-sm border px-2 py-1 text-sm"
              value={evidence}
              maxLength={4000}
              onChange={(event) => {
                setEvidence(event.target.value);
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
          value={errorCode}
          onChange={(event) => {
            setErrorCode(event.target.value);
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
          maxLength={MAX_DIAGNOSTICS}
          onChange={(event) => {
            setDiagnostics(event.target.value.slice(0, MAX_DIAGNOSTICS));
            setPreviewed(false);
            setConsent(false);
          }}
        />
        <p className="text-muted-foreground text-xs">{labels.previewHint}</p>
      </div>

      <Button
        type="button"
        variant="outline"
        onClick={() => {
          setPreviewed(true);
        }}
      >
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
            setConsent(event.target.checked);
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
              setVulnerability(event.target.checked);
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
    </form>
  );
}
