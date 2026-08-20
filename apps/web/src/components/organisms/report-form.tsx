"use client";

import { useState, useTransition } from "react";
import { useRouter } from "@/lib/i18n/navigation";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { MutationReference } from "@/components/molecules/mutation-reference";
import { createReportAction } from "@/actions/reports";

type ReportFormProps = {
  csrfToken: string;
  defaults: {
    objectKind: "component" | "setup" | "";
    stableId: string;
    version: string;
    contentDigest: string;
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
  };
};

const MAX_DIAGNOSTICS = 4000;

export function ReportForm({ csrfToken, defaults, labels }: ReportFormProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [diagnostics, setDiagnostics] = useState("");
  const [previewed, setPreviewed] = useState(false);
  const [consent, setConsent] = useState(false);
  const [vulnerability, setVulnerability] = useState(false);
  const [errorCode, setErrorCode] = useState("");
  const [showPreview, setShowPreview] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [operationId, setOperationId] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const objectKind = defaults.objectKind;
  const canSubmit =
    (objectKind === "component" || objectKind === "setup") &&
    Boolean(defaults.stableId) &&
    Boolean(defaults.version) &&
    Boolean(defaults.contentDigest) &&
    previewed &&
    consent;

  return (
    <form
      className="border-border mx-auto max-w-lg space-y-4 rounded-lg border p-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (objectKind !== "component" && objectKind !== "setup") {
          setError(labels.needPreview);
          return;
        }
        if (!previewed || !consent) {
          setError(labels.needPreview);
          return;
        }
        setError(null);
        startTransition(async () => {
          try {
            const payload = {
              csrfToken,
              objectKind,
              stableId: defaults.stableId,
              version: defaults.version,
              contentDigest: defaults.contentDigest,
              diagnostics,
              diagnosticsPreviewed: previewed,
              vulnerability,
              ...(errorCode ? { errorCode } : {}),
            };
            const result = await createReportAction(payload);
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
        size="sm"
        onClick={() => {
          setShowPreview(true);
          setPreviewed(true);
        }}
      >
        {labels.preview}
      </Button>

      {showPreview ? (
        <pre className="bg-muted/40 border-border max-h-40 overflow-auto rounded-md border p-3 font-mono text-xs whitespace-pre-wrap">
          {diagnostics || "—"}
        </pre>
      ) : null}

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={consent}
          disabled={!previewed}
          onChange={(event) => {
            setConsent(event.target.checked);
          }}
          className="mt-1"
        />
        <span>{labels.consent}</span>
      </label>

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={vulnerability}
          onChange={(event) => {
            setVulnerability(event.target.checked);
          }}
          className="mt-1"
        />
        <span>{labels.vulnerability}</span>
      </label>

      <Button type="submit" disabled={pending || !canSubmit}>
        {pending ? labels.submitting : labels.create}
      </Button>

      {done ? (
        <p className="text-sm" role="status">
          {labels.created}
        </p>
      ) : null}
      <MutationReference label={labels.referenceId} operationId={operationId} />
      {error ? (
        <p className="text-destructive text-sm" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
