import { getTranslations, setRequestLocale } from "next-intl/server";

import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { TechnologyActivityPolicy } from "@/components/organisms/corporate-governance-controls";
import { readCorporateContext } from "@/lib/api/corporate";
import { readTechnologyCapabilities, readTechnologyLandscapePolicy } from "@/lib/api/technology";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function CorporateSettingsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/organization/admins/settings`);
  const session = (await sessionCookieValue()) ?? "";
  const t = await getTranslations("technology");
  const corporate = await getTranslations("corporate");
  const context = await readCorporateContext(session);
  if (!context)
    return <StatePanel kind="empty" title={t("activityPolicy")} description={t("empty")} />;
  const organizationId = context.organization.organization_id;
  const permissions = await readTechnologyCapabilities(session, organizationId);
  if (
    !permissions.capabilities.includes("landscape.manage") ||
    !permissions.capabilities.includes("landscape.read")
  )
    return <StatePanel kind="error" title={t("activityPolicy")} description={t("forbidden")} />;
  let policy;
  try {
    policy = await readTechnologyLandscapePolicy(session, organizationId);
  } catch {
    return <StatePanel kind="error" title={t("activityPolicy")} description={t("unavailable")} />;
  }
  return (
    <div className="space-y-6">
      <HistoryBackButton
        label={corporate("backToWorkspace")}
        fallback="/corporate/organization/admins"
      />
      <TechnologyActivityPolicy
        policy={policy}
        organizationId={organizationId}
        authorizationRevision={permissions.authorization_revision}
        csrfToken={(await readCsrfToken()) ?? ""}
      />
    </div>
  );
}
