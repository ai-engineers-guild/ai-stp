import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { StatePanel } from "@/components/molecules/state-panel";
import { TechnologyActivityPolicy } from "@/components/organisms/corporate-governance-controls";
import { CorporateTelemetryPolicyControls } from "@/components/organisms/corporate-telemetry-policy-controls";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import { readCorporateContext } from "@/lib/api/corporate";
import { readTechnologyCapabilities, readTechnologyLandscapePolicy } from "@/lib/api/technology";
import type { CorporateTelemetryPolicyView } from "@/lib/api/generated/types.gen";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { PeopleHeader } from "@/app/[locale]/(site)/corporate/admins/people-shared";

export default async function CorporateSettingsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/admins/settings`);
  const session = (await sessionCookieValue()) ?? "";
  const t = await getTranslations("technology");
  const hub = await getTranslations("hub");
  const context = await readCorporateContext(session);
  if (!context)
    return <StatePanel kind="empty" title={t("organizationSettings")} description={t("empty")} />;
  const organizationId = context.organization.organization_id;
  const permissions = await readTechnologyCapabilities(session, organizationId);
  const canManageLandscape =
    permissions.capabilities.includes("landscape.manage") &&
    permissions.capabilities.includes("landscape.read");
  const canManageTelemetry =
    context.capabilities.includes("telemetry.read") &&
    context.capabilities.includes("telemetry.manage");
  if (!canManageLandscape && !canManageTelemetry)
    return (
      <StatePanel kind="error" title={t("organizationSettings")} description={t("forbidden")} />
    );

  let landscapePolicy = null;
  let landscapeUnavailable = false;
  if (canManageLandscape) {
    try {
      landscapePolicy = await readTechnologyLandscapePolicy(session, organizationId);
    } catch {
      landscapeUnavailable = true;
    }
  }

  let telemetryPolicy: CorporateTelemetryPolicyView | null = null;
  let telemetryUnavailable = false;
  if (canManageTelemetry) {
    try {
      telemetryPolicy = await apiRequest<CorporateTelemetryPolicyView>(
        `/v1/corporate/organizations/${organizationId}/telemetry/policy`,
        { sessionToken: session },
      );
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) telemetryUnavailable = true;
    }
  }
  const authority = {
    organizationId,
    authorizationRevision: permissions.authorization_revision,
    csrfToken: (await readCsrfToken()) ?? "",
  };
  return (
    <div className="min-w-0 space-y-6">
      <PeopleHeader section={hub("organization")} current={t("organizationSettings")}>
        <Badge variant="secondary">{context.member.role}</Badge>
      </PeopleHeader>

      {canManageTelemetry &&
        (telemetryUnavailable ? (
          <StatePanel
            kind="error"
            title={t("telemetryPolicy")}
            description={t("telemetryUnavailable")}
          />
        ) : (
          <CorporateTelemetryPolicyControls
            policy={telemetryPolicy}
            {...authority}
            authorizationRevision={context.organization.authorization_revision}
          />
        ))}
      {canManageLandscape &&
        (landscapeUnavailable || !landscapePolicy ? (
          <StatePanel kind="error" title={t("activityPolicy")} description={t("unavailable")} />
        ) : (
          <TechnologyActivityPolicy policy={landscapePolicy} {...authority} />
        ))}
    </div>
  );
}
