import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateJobTitles } from "@/components/organisms/corporate-job-titles";
import { readCorporateWorkspace } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";

export default async function JobTitlesPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/job-titles`);
  const t = await getTranslations("corporate");
  const people = await getTranslations("people");
  const common = await getTranslations("common");
  let workspace;
  try {
    workspace = await readCorporateWorkspace((await sessionCookieValue()) ?? "", false);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel kind="error" title={t("jobTitles")} description={common("apiUnavailable")} />
    );
  }
  if (!workspace)
    return <StatePanel kind="empty" title={t("jobTitles")} description={t("noOrganization")} />;
  if (!workspace.context.capabilities.includes("job_title.list"))
    return <StatePanel kind="empty" title={t("jobTitles")} description={common("accessDenied")} />;
  return (
    <div className="min-w-0 space-y-5">
      <header className="space-y-3">
        <nav
          aria-label={people("breadcrumbs")}
          className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs sm:text-sm"
        >
          <Link href="/corporate/overview" className="hover:text-foreground">
            {people("corporate")}
          </Link>
          <span aria-hidden>/</span>
          <span>{people("administration")}</span>
          <span aria-hidden>/</span>
          <span>{people("referenceData")}</span>
          <span aria-hidden>/</span>
          <span aria-current="page" className="text-foreground">
            {t("jobTitles")}
          </span>
        </nav>
        <div className="space-y-1">
          <h1 className="text-3xl leading-tight font-medium tracking-tight">{t("jobTitles")}</h1>
          <p className="text-muted-foreground text-sm sm:text-base">
            {t("jobTitlesDescription")}
          </p>
        </div>
      </header>
      <CorporateJobTitles
        csrfToken={(await readCsrfToken()) ?? ""}
        organizationId={workspace.context.organization.organization_id}
        authorizationRevision={workspace.context.organization.authorization_revision}
        capabilities={workspace.context.capabilities}
        jobTitles={workspace.jobTitles?.items ?? []}
        members={workspace.members?.items ?? null}
      />
    </div>
  );
}
