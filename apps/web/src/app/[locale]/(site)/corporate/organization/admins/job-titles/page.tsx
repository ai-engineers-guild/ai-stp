import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { CorporateAdminPanel } from "@/components/organisms/corporate-admin-panel";
import { readCorporateWorkspace } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function JobTitlesPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/job-titles`);
  const workspace = await readCorporateWorkspace((await sessionCookieValue()) ?? "", false);
  if (!workspace?.context.capabilities.includes("job_title.list")) notFound();
  const t = await getTranslations("corporate");
  return (
    <div className="min-w-0 space-y-6">
      <HistoryBackButton label={t("backToWorkspace")} fallback="/corporate/organization/admins" />
      <header className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{t("jobTitles")}</h1>
        <p className="text-muted-foreground">{t("jobTitlesDescription")}</p>
      </header>
      <CorporateAdminPanel
        jobTitlesOnly
        csrfToken={(await readCsrfToken()) ?? ""}
        organizationId={workspace.organization.organization_id}
        authorizationRevision={workspace.context.organization.authorization_revision}
        permissions={workspace.context.capabilities}
        jobTitles={workspace.jobTitles?.items ?? []}
        labels={{
          title: t("jobTitles"),
          description: t("jobTitlesDescription"),
          members: t("members"),
          projects: t("projects"),
          teams: t("teams"),
          roles: t("roles"),
          displayName: t("displayName"),
          email: t("email"),
          name: t("name"),
          role: t("organizationRole"),
          parentRole: t("parentRole"),
          permissions: t("permissions"),
          create: t("create"),
          creating: t("creating"),
          saved: t("saved"),
          failed: t("failed"),
          staff: t("staff"),
          lead: t("lead"),
          jobTitles: t("jobTitles"),
          jobTitleName: t("jobTitleName"),
          jobTitleDescription: t("jobTitleDescription"),
          jobTitleState: t("jobTitleState"),
          jobTitleCurrent: t("jobTitleCurrent"),
          jobTitleRetired: t("jobTitleRetired"),
          jobTitleSave: t("jobTitleSave"),
          jobTitleNoItems: t("jobTitleNoItems"),
        }}
      />
    </div>
  );
}
