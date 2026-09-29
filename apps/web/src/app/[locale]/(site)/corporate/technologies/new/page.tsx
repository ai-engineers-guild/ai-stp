import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { TechnologyRegistryCreate } from "@/components/organisms/technology-registry-create";
import { ApiError } from "@/lib/api/errors";
import { readTechnologyDirectory } from "@/lib/api/technology";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";

export default async function NewTechnologyPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/technologies/new`);
  const t = await getTranslations("technology");
  const c = await getTranslations("corporate");
  let registry;
  try {
    registry = await readTechnologyDirectory((await sessionCookieValue()) ?? "", {
      page: 1,
      pageSize: 1,
    });
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel kind="error" title={t("registry")} description={t("registryUnavailable")} />
    );
  }
  if (!registry)
    return <StatePanel kind="empty" title={t("registry")} description={c("noOrganization")} />;
  if (!registry.permissions.capabilities.includes("technology.create"))
    return <StatePanel kind="empty" title={t("registry")} description={t("notPermitted")} />;
  return (
    <div className="min-w-0 space-y-6">
      <header className="space-y-2">
        <Link
          href="/corporate/technologies"
          className="text-primary text-sm underline underline-offset-4"
        >
          {t("backToTechnologies")}
        </Link>
        <h1 className="text-4xl font-medium tracking-tight">{t("createTechnology")}</h1>
      </header>
      <TechnologyRegistryCreate
        kind="technology"
        organizationId={registry.organization.organization_id}
        authorizationRevision={registry.permissions.authorization_revision}
        csrfToken={(await readCsrfToken()) ?? ""}
        categories={registry.categories?.items ?? null}
      />
    </div>
  );
}
