import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { Badge } from "@/components/atoms/badge";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { readOwnReport } from "@/lib/api/reports";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
export default async function ReportCasePage({
  params,
}: {
  params: Promise<{ locale: string; caseId: string }>;
}) {
  const { locale, caseId } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/reports/${caseId}`);
  const t = await getTranslations("reports");
  const tc = await getTranslations("common");
  let report;
  try {
    report = await readOwnReport((await sessionCookieValue()) ?? "", caseId);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) notFound();
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }
  const topicKey = `topic${report.topic
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("")}`;
  const stateKey = `state${report.state.charAt(0).toUpperCase()}${report.state.slice(1)}`;
  const topic = t.has(topicKey) ? t(topicKey) : report.topic;
  const state = t.has(stateKey) ? t(stateKey) : report.state;
  const publicResponse = typeof report.public_response === "string" ? report.public_response : "";
  return (
    <article className="mx-auto max-w-3xl space-y-6">
      <HistoryBackButton label={t("backToReports")} fallback="/reports" />
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            {topic}
          </p>
          <Badge variant="outline">{state}</Badge>
        </div>
        <h1 className="text-3xl font-medium tracking-tight">{t("caseDetails")}</h1>
        <p className="text-muted-foreground font-mono text-xs break-all">{report.case_id}</p>
      </header>
      <section
        className="border-border space-y-3 rounded-lg border p-4"
        aria-labelledby="case-target"
      >
        <h2 id="case-target" className="text-lg font-medium">
          {t("caseTarget")}
        </h2>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">{t("objectKind")}</dt>
            <dd>{report.object_kind || t("notApplicable")}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{t("stableId")}</dt>
            <dd className="break-all">{report.stable_id || t("notApplicable")}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{t("version")}</dt>
            <dd>{report.version || t("notApplicable")}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">{t("submitted")}</dt>
            <dd>
              {new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(
                new Date(report.created_at),
              )}
            </dd>
          </div>
        </dl>
      </section>
      <section
        className="border-primary/30 bg-primary/5 space-y-2 rounded-lg border p-4"
        aria-labelledby="case-response"
      >
        <h2 id="case-response" className="text-lg font-medium">
          {t("publicResponse")}
        </h2>
        <p
          className={
            publicResponse ? "text-sm whitespace-pre-wrap" : "text-muted-foreground text-sm"
          }
        >
          {publicResponse || t("responsePending")}
        </p>
      </section>
      <section
        className="border-border space-y-3 rounded-lg border p-4"
        aria-labelledby="case-status"
      >
        <h2 id="case-status" className="text-lg font-medium">
          {t("statusHistory")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("statusHistoryNote")}</p>
        <div className="flex items-center gap-3 text-sm">
          <span className="bg-primary h-2 w-2 rounded-full" aria-hidden="true" />
          {state}
        </div>
      </section>
    </article>
  );
}
