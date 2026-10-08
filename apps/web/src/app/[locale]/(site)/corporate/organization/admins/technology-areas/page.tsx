import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { AreaLifecycleControls } from "@/components/organisms/corporate-governance-controls";
import { TechnologyRegistryCreate } from "@/components/organisms/technology-registry-create";
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
  await requireSession(locale, `/${locale}/corporate/organization/admins/technology-areas`);
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
  const mutation = {
    organizationId,
    authorizationRevision: directory.permissions.authorization_revision,
    csrfToken: (await readCsrfToken()) ?? "",
  };
  const canCreate = directory.permissions.capabilities.includes("category.create");
  const canUpdate = directory.permissions.capabilities.includes("category.update");
  const canRemove = directory.permissions.capabilities.includes("category.delete");
  return (
    <div className="min-w-0 space-y-6">
      <header className="space-y-3">
        <HistoryBackButton label={h("referenceData")} fallback="/corporate/organization/admins" />
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{t("areas.title")}</h1>
        <p className="text-muted-foreground max-w-prose">{t("areas.description")}</p>
      </header>
      {canCreate && (
        <details>
          <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
            {t("areas.create")}
          </summary>
          <TechnologyRegistryCreate kind="area" categories={null} {...mutation} />
        </details>
      )}
      {directory.areas.items.length ? (
        <ul className="divide-border divide-y">
          {directory.areas.items.map((area) => (
            <li key={area.area_id} className="space-y-1 py-4">
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{area.name}</span>
                {area.state && area.state !== "active" && (
                  <Badge variant={area.state === "draft" ? "warning" : "secondary"}>
                    {t(`values.${area.state}`)}
                  </Badge>
                )}
              </span>
              <p className="text-muted-foreground max-w-prose text-sm">{area.description}</p>
              {canUpdate && (
                <details>
                  <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
                    {t("areas.edit")}
                  </summary>
                  <TechnologyRegistryCreate
                    kind="area"
                    categories={null}
                    initialArea={area}
                    {...mutation}
                  />
                </details>
              )}
              <AreaLifecycleControls
                area={area}
                canRemove={canRemove}
                canRestore={canUpdate}
                {...mutation}
              />
            </li>
          ))}
        </ul>
      ) : (
        <StatePanel kind="empty" title={t("areas.title")} description={t("areas.empty")} />
      )}
    </div>
  );
}
