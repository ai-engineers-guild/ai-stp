import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateJobTitles } from "@/components/organisms/corporate-job-titles";
import { readCorporateWorkspace } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { PeopleHeader } from "@/app/[locale]/(site)/corporate/admin/people-shared";

export default async function JobTitlesPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/admin/job-titles`);
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
      <PeopleHeader
        section={people("referenceData")}
        current={t("jobTitles")}
        description={t("jobTitlesDescription")}
      />
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
