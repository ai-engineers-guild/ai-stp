import { useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
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
import { Link } from "@/lib/i18n/navigation";

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
    return <StatePanel kind="empty" title={t("organizationSettings")} description={t("empty")} />;
  const organizationId = context.organization.organization_id;
  const permissions = await readTechnologyCapabilities(session, organizationId);
  const canManageLandscape =
    permissions.capabilities.includes("landscape.manage") &&
    permissions.capabilities.includes("landscape.read");
  const canManageTelemetry =
    context.capabilities.includes("telemetry.read") &&
    context.capabilities.includes("telemetry.manage");
  const canManageGit = context.capabilities.some((permission) =>
    permission.startsWith("connector."),
  );
  if (!canManageLandscape && !canManageTelemetry && !canManageGit)
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
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
            {t("organizationSettings")}
          </h1>
          <Badge variant="secondary">{context.member.role}</Badge>
        </div>
      </header>
      <HistoryBackButton
        label={corporate("backToWorkspace")}
        fallback="/corporate/organization/admins"
      />

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
      {canManageGit ? <GitManagementSection capabilities={context.capabilities} /> : null}
    </div>
  );
}

function GitManagementSection({ capabilities }: { capabilities: readonly string[] }) {
  const t = useTranslations("corporate");
  const providers = (
    [
      { key: "github", name: t("gitProviderGithub"), href: "/account/github" },
      { key: "gitlab", name: t("gitProviderGitlab"), href: "/corporate/gitlab" },
    ] as const
  ).map((provider) => ({
    ...provider,
    grants: ["use", "read", "write", "create", "visibility", "access"].filter((action) =>
      capabilities.includes(`connector.${provider.key}.${action}`),
    ),
  }));
  return (
    <section className="border-border bg-card min-w-0 space-y-4 rounded-lg border p-5 shadow-sm sm:p-6">
      <div className="space-y-1">
        <h2 className="text-xl font-medium">{t("gitManagement")}</h2>
        <p className="text-muted-foreground max-w-2xl text-sm">{t("gitManagementBody")}</p>
      </div>
      <ul className="divide-border divide-y">
        {providers.map((provider) => (
          <li
            key={provider.key}
            className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
          >
            <div className="min-w-0">
              <p className="font-medium">{provider.name}</p>
              <p className="text-muted-foreground text-xs">
                {provider.grants.map((grant) => `connector.${provider.key}.${grant}`).join(" · ") ||
                  t("gitNoGrants")}
              </p>
            </div>
            <Link href={provider.href} className="text-sm underline underline-offset-4">
              {t("gitManageProvider")}
            </Link>
          </li>
        ))}
      </ul>
      <p className="text-muted-foreground text-xs">
        {t("gitGrantsHint")}{" "}
        <Link href="/corporate/organization/admins/roles" className="underline underline-offset-4">
          {t("gitGrantsLink")}
        </Link>
      </p>
    </section>
  );
}
