import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { ReportForm } from "@/components/organisms/report-form";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { listOwnReports } from "@/lib/api/reports";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{
    object_kind?: string;
    stable_id?: string;
    version?: string;
    digest?: string;
  }>;
};

export default async function ReportsPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const sp = await searchParams;
  setRequestLocale(locale);
  const returnQuery = new URLSearchParams();
  if (sp.object_kind) returnQuery.set("object_kind", sp.object_kind);
  if (sp.stable_id) returnQuery.set("stable_id", sp.stable_id);
  if (sp.version) returnQuery.set("version", sp.version);
  if (sp.digest) returnQuery.set("digest", sp.digest);
  const returnTo = `/${locale}/reports${returnQuery.size ? `?${returnQuery.toString()}` : ""}`;
  await requireSession(locale, returnTo);
  const t = await getTranslations("reports");
  const tc = await getTranslations("common");
  const token = await sessionCookieValue();
  const csrf = await readCsrfToken();

  let cases;
  try {
    cases = await listOwnReports(token ?? "");
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  if (!csrf) {
    return <StatePanel kind="error" title={tc("sessionExpired")} description={tc("login")} />;
  }

  const kind = sp.object_kind === "component" || sp.object_kind === "setup" ? sp.object_kind : "";
  const hasTarget = Boolean(kind && sp.stable_id && sp.version && sp.digest);

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground max-w-2xl text-sm">{t("subtitle")}</p>
      </div>

      {hasTarget ? (
        <ReportForm
          csrfToken={csrf}
          defaults={{
            objectKind: kind,
            stableId: sp.stable_id ?? "",
            version: sp.version ?? "",
            contentDigest: sp.digest ?? "",
          }}
          labels={{
            create: t("create"),
            submitting: t("submitting"),
            preview: t("preview"),
            previewHint: t("previewHint"),
            consent: t("consent"),
            diagnostics: t("diagnostics"),
            vulnerability: t("vulnerability"),
            objectKind: t("objectKind"),
            stableId: t("stableId"),
            version: t("version"),
            digest: t("digest"),
            errorCode: t("errorCode"),
            needPreview: t("needPreview"),
            created: t("created"),
            referenceId: tc("referenceId"),
          }}
        />
      ) : (
        <p className="text-muted-foreground text-sm">{t("missingTarget")}</p>
      )}

      <section className="space-y-3" aria-labelledby="own-cases-heading">
        <h2 id="own-cases-heading" className="text-lg font-medium tracking-tight">
          {t("ownCases")}
        </h2>
        {cases.items.length === 0 ? (
          <StatePanel kind="empty" title={tc("empty")} description={t("empty")} />
        ) : (
          <ul className="divide-border border-border divide-y rounded-lg border">
            {cases.items.map((item) => (
              <li
                key={item.case_id}
                className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="space-y-1">
                  <p className="font-mono text-xs">{item.case_id}</p>
                  <p className="text-muted-foreground font-mono text-xs">
                    {item.object_kind} / {item.stable_id} / {item.version}
                  </p>
                </div>
                <Badge variant="outline" className="font-mono text-xs">
                  {item.state}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
