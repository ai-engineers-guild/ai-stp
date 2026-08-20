import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { StaffCaseActions } from "@/components/organisms/staff-case-actions";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { readStaffReport } from "@/lib/api/reports";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";

type PageProps = {
  params: Promise<{ locale: string; caseId: string }>;
};

export default async function StaffReportDetailPage({ params }: PageProps) {
  const { locale, caseId } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/staff/reports/${caseId}`);
  const t = await getTranslations("staff");
  const tc = await getTranslations("common");
  const token = await sessionCookieValue();
  const csrf = await readCsrfToken();

  let detail;
  try {
    detail = await readStaffReport(token ?? "", caseId);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 403 || error.code === "AI_STP_FORBIDDEN")) {
      return <StatePanel kind="error" title={t("forbidden")} description={t("subtitle")} />;
    }
    if (error instanceof ApiError && (error.status === 404 || error.status === 403)) {
      return <StatePanel kind="error" title={tc("notFound")} description={t("notFound")} />;
    }
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  if (!csrf) {
    return <StatePanel kind="error" title={tc("sessionExpired")} description={tc("login")} />;
  }

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{t("caseDetail")}</h1>
        <p className="text-muted-foreground font-mono text-xs">{detail.case_id}</p>
      </div>

      <dl className="bg-muted/40 border-border grid gap-3 rounded-lg border p-4 sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground font-mono text-xs">{t("state")}</dt>
          <dd>
            <Badge variant="outline" className="font-mono text-xs">
              {detail.state}
            </Badge>
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground font-mono text-xs">{t("vulnerability")}</dt>
          <dd className="font-mono text-sm">{detail.vulnerability ? tc("yes") : tc("no")}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground font-mono text-xs">object</dt>
          <dd className="font-mono text-xs">
            {detail.object_kind} / {detail.stable_id} / {detail.version}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-muted-foreground font-mono text-xs">digest</dt>
          <dd className="font-mono text-xs break-all">{detail.content_digest ?? "—"}</dd>
        </div>
        {detail.error_code ? (
          <div>
            <dt className="text-muted-foreground font-mono text-xs">error_code</dt>
            <dd className="font-mono text-xs">{detail.error_code}</dd>
          </div>
        ) : null}
        {detail.harness_id ? (
          <div>
            <dt className="text-muted-foreground font-mono text-xs">harness_id</dt>
            <dd className="font-mono text-xs">{detail.harness_id}</dd>
          </div>
        ) : null}
      </dl>

      <StaffCaseActions
        csrfToken={csrf}
        caseId={detail.case_id}
        objectKind={detail.object_kind}
        stableId={detail.stable_id}
        version={detail.version}
        labels={{
          triage: t("triage"),
          reason: t("reason"),
          confirm: t("confirm"),
          block: t("block"),
          hide: t("hide"),
          restore: t("restore"),
          authorVerifiedIssue: t("authorVerifiedIssue"),
          authorVerifiedRevoke: t("authorVerifiedRevoke"),
          subjectAccount: t("subjectAccount"),
          lifecycle: t("lifecycle"),
          referenceId: tc("referenceId"),
        }}
      />
    </div>
  );
}
