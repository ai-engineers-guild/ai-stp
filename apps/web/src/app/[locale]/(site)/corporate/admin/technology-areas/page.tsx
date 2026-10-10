import { getTranslations, setRequestLocale } from "next-intl/server";

import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { TaxonomyDirectory } from "@/components/organisms/taxonomy-directory";
import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { readTechnologyAreaDirectory } from "@/lib/api/technology-scans";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function TechnologyAreasPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/admin/technology-areas`);
  const session = (await sessionCookieValue()) ?? "";
  const t = await getTranslations("technology");
  const h = await getTranslations("hub");
  const c = await getTranslations("corporate");
  const common = await getTranslations("common");
  let context;
  try {
    context = await readCorporateContext(session);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel kind="error" title={t("areas.title")} description={common("apiUnavailable")} />
    );
  }
  if (!context)
    return <StatePanel kind="empty" title={t("areas.title")} description={c("noOrganization")} />;
  const organizationId = context.organization.organization_id;
  let directory;
  try {
    directory = await readTechnologyAreaDirectory(session, organizationId);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel
        kind="error"
        title={t("areas.title")}
        description={error.status === 403 ? t("forbidden") : t("unavailable")}
      />
    );
  }
  if (!directory)
    return <StatePanel kind="empty" title={t("areas.title")} description={t("notPermitted")} />;
  const capabilities = directory.permissions.capabilities;
  return (
    <div className="min-w-0 space-y-6">
      <header className="space-y-3">
        <HistoryBackButton label={h("referenceData")} fallback="/corporate/admin" />
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{t("areas.title")}</h1>
        <p className="text-muted-foreground max-w-prose">{t("areas.description")}</p>
      </header>
      <TaxonomyDirectory
        kind="area"
        items={directory.areas.items}
        areas={directory.areas.items}
        categories={directory.categories?.items ?? []}
        authority={{
          organizationId,
          authorizationRevision: directory.permissions.authorization_revision,
          csrfToken: (await readCsrfToken()) ?? "",
        }}
        canCreate={capabilities.includes("area.create")}
        canUpdate={capabilities.includes("area.update")}
        canRemove={capabilities.includes("area.delete")}
      />
    </div>
  );
}
