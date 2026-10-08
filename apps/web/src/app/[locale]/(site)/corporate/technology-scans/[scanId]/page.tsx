import { getTranslations, setRequestLocale } from "next-intl/server";
import { StatePanel } from "@/components/molecules/state-panel";
import { TechnologyScanFindings } from "@/components/organisms/technology-scan-findings";
import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { readTechnologyReviewWorkspace } from "@/lib/api/technology-scans";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function TechnologyReviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; scanId?: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale, scanId } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/technology-scans/${scanId}`);
  const session = (await sessionCookieValue()) ?? "",
    t = await getTranslations("technology");
  let context;
  let data;
  try {
    context = await readCorporateContext(session);

    if (context)
      data = await readTechnologyReviewWorkspace(
        session,
        context.organization.organization_id,
        scanId,
      );
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel
        kind="error"
        title={t("mappingTitle")}
        description={error.status === 403 ? t("forbidden") : t("unavailable")}
      />
    );
  }
  if (!context)
    return <StatePanel kind="empty" title={t("mappingTitle")} description={t("empty")} />;
  if (!data)
    return <StatePanel kind="empty" title={t("mappingTitle")} description={t("notPermitted")} />;
  const query = await searchParams;
  return (
    <div className="technology-workspace">
      <TechnologyScanFindings
        organizationId={context.organization.organization_id}
        authorizationRevision={data.permissions.authorization_revision}
        csrfToken={(await readCsrfToken()) ?? ""}
        scans={data.scans}
        technologies={data.technologies?.items ?? []}
        categories={data.categories?.items ?? null}
        areas={data.areas?.items ?? null}
        projects={context.projects}
        mode="scan"
        initialScan={typeof query.scan_id === "string" ? query.scan_id : ""}
        canUpdate={data.permissions.capabilities.includes("technology.update")}
      />
    </div>
  );
}
