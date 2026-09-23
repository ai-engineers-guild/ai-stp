import { getTranslations, setRequestLocale } from "next-intl/server";

import { InstallationsTable } from "@/components/installations/installations-table";
import type { InstallationHeartbeatList } from "@/components/installations/types";
import { StatePanel } from "@/components/molecules/state-panel";
import { readCorporateOrganization } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";

export default async function CorporateInstallationsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("installations");
  await requireSession(locale, `/${locale}/corporate/installations`);

  const token = await sessionCookieValue();
  const organization = token ? await readCorporateOrganization(token) : null;
  if (!token || !organization) {
    return <StatePanel kind="empty" title={t("emptyOrganization")} />;
  }

  let list: InstallationHeartbeatList | null = null;
  try {
    list = await apiRequest<InstallationHeartbeatList>(
      `/v1/corporate/organizations/${organization.organization_id}/telemetry/heartbeats`,
      { sessionToken: token },
    );
  } catch (error) {
    if (error instanceof ApiError) {
      return <StatePanel kind="error" title={t("unavailable")} description={error.message} />;
    }
    throw error;
  }

  if (list.items.length === 0) {
    return <StatePanel kind="empty" title={t("empty")} description={t("emptyDescription")} />;
  }

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-8">
      <h1 className="mb-6 text-xl font-semibold">{t("title")}</h1>
      <InstallationsTable
        items={list.items}
        labels={{
          account: t("account"),
          device: t("device"),
          cli: t("cli"),
          lastSync: t("lastSync"),
          health: t("health"),
          never: t("never"),
        }}
      />
    </main>
  );
}
