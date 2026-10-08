import { getTranslations, setRequestLocale } from "next-intl/server";
import { StatePanel } from "@/components/molecules/state-panel";
import { TechnologyScanLaunch } from "@/components/organisms/technology-scan-launch";
import { TechnologyScanJournal } from "@/components/organisms/technology-scan-journal";
import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { readTechnologyScanJournal } from "@/lib/api/technology-scans";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

export default async function TechnologyScansPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/technology-scans`);
  const session = (await sessionCookieValue()) ?? "",
    t = await getTranslations("technology"),
    s = await getTranslations("technology.scans"),
    w = await getTranslations("technology.workspace");
  let context;
  let journal;
  try {
    context = await readCorporateContext(session);

    if (context)
      journal = await readTechnologyScanJournal(session, context.organization.organization_id);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel
        kind="error"
        title={s("title")}
        description={error.status === 403 ? t("forbidden") : t("unavailable")}
      />
    );
  }
  if (!context) return <StatePanel kind="empty" title={s("title")} description={t("empty")} />;
  if (!journal)
    return <StatePanel kind="empty" title={s("title")} description={t("notPermitted")} />;
  const query = await searchParams;
  return (
    <div className="technology-workspace space-y-5">
      <div className="technology-page-actions">
        <Link
          href="/corporate/technology-landscape"
          className="inline-flex min-h-11 items-center gap-2 text-sm font-medium"
        >
          <Icon name="arrowLeft" size="sm" />
          {w("backLandscape")}
        </Link>
        {journal.permissions.capabilities.includes("technology.scan_publish") && (
          <TechnologyScanLaunch
            organizationId={context.organization.organization_id}
            authorizationRevision={journal.permissions.authorization_revision}
            csrfToken={(await readCsrfToken()) ?? ""}
            projects={context.projects}
            variant="outline"
          />
        )}
      </div>
      <header className="space-y-2">
        <h1>{s("title")}</h1>
        <p className="text-muted-foreground text-sm">{w("journalDescription")}</p>
      </header>
      <TechnologyScanJournal
        items={journal.scans.items}
        projects={context.projects}
        initialProject={typeof query.project_id === "string" ? query.project_id : ""}
      />
    </div>
  );
}
