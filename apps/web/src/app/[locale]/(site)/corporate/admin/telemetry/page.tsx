import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import {
  CorporateTelemetryPolicyControls,
  type TelemetryPolicyTab,
} from "@/components/organisms/corporate-telemetry-policy-controls";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import { readCorporateContext } from "@/lib/api/corporate";
import type { CorporateTelemetryPolicyView } from "@/lib/api/generated/types.gen";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { PeopleHeader } from "@/app/[locale]/(site)/corporate/admin/people-shared";

const TELEMETRY_TABS: readonly TelemetryPolicyTab[] = ["heartbeat", "usage", "retention"];

export default async function CorporateTelemetryPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/admin/telemetry`);
  const session = (await sessionCookieValue()) ?? "";
  const t = await getTranslations("technology");
  const hub = await getTranslations("hub");
  const context = await readCorporateContext(session);
  if (!context)
    return <StatePanel kind="empty" title={hub("telemetry")} description={hub("empty")} />;
  if (!context.capabilities.includes("telemetry.read"))
    return <StatePanel kind="error" title={hub("telemetry")} description={t("forbidden")} />;
  const organizationId = context.organization.organization_id;
  const canManage = context.capabilities.includes("telemetry.manage");

  const { tab: rawTab } = await searchParams;
  const tab = (
    typeof rawTab === "string" && TELEMETRY_TABS.includes(rawTab as TelemetryPolicyTab)
      ? rawTab
      : "heartbeat"
  ) as TelemetryPolicyTab;

  let policy: CorporateTelemetryPolicyView | null = null;
  let unavailable = false;
  try {
    policy = await apiRequest<CorporateTelemetryPolicyView>(
      `/v1/corporate/organizations/${organizationId}/telemetry/policy`,
      { sessionToken: session },
    );
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 404)) unavailable = true;
  }
  return (
    <div className="min-w-0 space-y-6">
      <PeopleHeader
        section={hub("organization")}
        current={hub("telemetry")}
        description={t("telemetryPageDescription")}
      />
      {unavailable ? (
        <StatePanel
          kind="error"
          title={t("telemetryPolicy")}
          description={t("telemetryUnavailable")}
        />
      ) : (
        <CorporateTelemetryPolicyControls
          policy={policy}
          tab={tab}
          canManage={canManage}
          organizationId={organizationId}
          authorizationRevision={context.organization.authorization_revision}
          csrfToken={(await readCsrfToken()) ?? ""}
        />
      )}
    </div>
  );
}
